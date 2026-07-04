"""
LLM-слой обоснования (опциональный, поверх интерпретируемого ядра).

Роль LLM — НЕ придумывать гипотезы, а красиво и связно СФОРМУЛИРОВАТЬ
обоснование строго по фактам, которые ему передаёт детерминированное ядро
(диагноз, числа, механизм, цитаты). Так мы получаем «живой» экспертный текст
без галлюцинаций: все числа и утверждения приходят из данных, LLM только
переписывает их в профессиональную прозу.

Три бэкенда, выбираются по доступности (fallback-цепочка):
  1) Yandex AI Studio (YandexGPT) по API — ОСНОВНОЙ, если задан YANDEX_API_KEY
     (+ YANDEX_FOLDER_ID). Организаторы выдают безлимитный доступ по API-ключу.
  2) Локальная модель (Qwen3 из HF-кэша, офлайн) — фолбэк без интернета.
  3) Нет ни того, ни другого → слой отключается, ядро берёт детерминированный текст.

Ключ и folder id задаются переменными окружения:
    YANDEX_API_KEY=...        (обязательно для Yandex-бэкенда)
    YANDEX_FOLDER_ID=...      (обязательно для Yandex-бэкенда)
    YANDEX_MODEL=yandexgpt    (опц.: yandexgpt | yandexgpt-lite | llama и т.п.)
"""
from __future__ import annotations
import os
import json

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

# Подхватываем .env (ключ Yandex) при любом способе запуска.
try:
    from core import load_dotenv
    load_dotenv()
except Exception:
    pass

# Локальные модели-кандидаты (берём первую полностью скачанную в HF-кэше).
CANDIDATES = [
    "Qwen/Qwen3-4B-Instruct-2507",
    "Qwen/Qwen3-1.7B",
    "Qwen/Qwen3-0.6B",
]

SYSTEM = (
    "Ты — старший инженер-технолог обогатительной фабрики (флотация сульфидных "
    "руд цветных металлов). Твоя задача — по предоставленным ФАКТАМ написать "
    "профессиональное обоснование инженерной гипотезы. Пиши строго по-русски, "
    "3-5 предложений, деловым техническим языком. КРИТИЧЕСКИ ВАЖНО: используй "
    "только числа и утверждения из блока ФАКТЫ, ничего не выдумывай, не добавляй "
    "новых числовых значений. Не используй маркдаун и списки — только связный абзац."
)

# Эндпоинт Yandex Foundation Models (AI Studio), синхронный completion.
YANDEX_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


# ----------------------------- Yandex-бэкенд ---------------------------------

class YandexBackend:
    """YandexGPT через AI Studio REST API. Только stdlib (urllib) — без доп. пакетов."""

    def __init__(self):
        self.ok = False
        self.name = None
        self.device = "yandex-api"
        self._err = ""
        self.api_key = os.environ.get("YANDEX_API_KEY", "").strip()
        self.folder = os.environ.get("YANDEX_FOLDER_ID", "").strip()
        self.model = os.environ.get("YANDEX_MODEL", "yandexgpt").strip()

    def load(self):
        if not self.api_key or not self.folder:
            self._err = "нет YANDEX_API_KEY / YANDEX_FOLDER_ID"
            return self
        # Не делаем сетевой probe при загрузке (может не быть интернета в момент
        # инициализации UI). Готовность подтвердит первый успешный refine().
        self.name = f"yandex:{self.model}"
        self.ok = True
        return self

    def _model_uri(self):
        # gpt://<folder>/<model>/latest
        return f"gpt://{self.folder}/{self.model}/latest"

    def refine(self, facts: str, max_new_tokens: int = 200) -> str:
        if not self.ok:
            return ""
        import urllib.request
        import urllib.error
        payload = {
            "modelUri": self._model_uri(),
            "completionOptions": {
                "stream": False,
                "temperature": 0.2,
                "maxTokens": str(max_new_tokens),
            },
            "messages": [
                {"role": "system", "text": SYSTEM},
                {"role": "user", "text": "ФАКТЫ:\n" + facts +
                 "\n\nНапиши обоснование гипотезы одним абзацем."},
            ],
        }
        import time
        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self.api_key}",
            "x-folder-id": self.folder,
        }
        # Ретраи с бэкоффом на 429 (лимит параллельных запросов) и 5xx.
        delays = [0.6, 1.5, 3.0]
        for attempt in range(len(delays) + 1):
            req = urllib.request.Request(YANDEX_URL, data=data_bytes,
                                         headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                alts = data.get("result", {}).get("alternatives", [])
                if alts:
                    self._err = ""
                    return alts[0].get("message", {}).get("text", "").strip()
                return ""
            except urllib.error.HTTPError as e:
                code = e.code
                self._err = f"Yandex HTTP {code}: {e.read()[:160]!r}"
                if code in (429, 500, 502, 503, 504) and attempt < len(delays):
                    time.sleep(delays[attempt])
                    continue
                return ""
            except Exception as e:
                self._err = f"Yandex ошибка: {e}"
                if attempt < len(delays):
                    time.sleep(delays[attempt])
                    continue
                return ""
        return ""


# ----------------------------- Локальный бэкенд ------------------------------

class LocalBackend:
    """Локальная causal-LM из HF-кэша (Qwen3). Офлайн, PyTorch."""

    def __init__(self):
        self.ok = False
        self.model = None
        self.tok = None
        self.device = "cpu"
        self.name = None
        self._err = ""

    def load(self):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except Exception as e:
            self._err = f"transformers/torch недоступны: {e}"
            return self
        name = self._find_cached()
        if not name:
            self._err = "нет полной модели в HF-кэше (offline)"
            return self
        try:
            if torch.cuda.is_available():
                self.device = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
            self.tok = AutoTokenizer.from_pretrained(name)
            dtype = torch.float16 if self.device != "cpu" else torch.float32
            self.model = AutoModelForCausalLM.from_pretrained(name, dtype=dtype).to(self.device)
            self.model.eval()
            self.name = name
            self.ok = True
        except Exception as e:
            self._err = f"ошибка загрузки {name}: {e}"
        return self

    def _find_cached(self):
        import glob
        hub = os.path.expanduser("~/.cache/huggingface/hub")
        for cand in CANDIDATES:
            folder = "models--" + cand.replace("/", "--")
            snaps = os.path.join(hub, folder, "snapshots")
            if not os.path.isdir(snaps):
                continue
            has_weights = glob.glob(os.path.join(snaps, "*", "*.safetensors"))
            has_cfg = glob.glob(os.path.join(snaps, "*", "config.json"))
            has_tok = glob.glob(os.path.join(snaps, "*", "tokenizer.json"))
            if has_weights and has_cfg and has_tok:
                return cand
        return None

    def refine(self, facts: str, max_new_tokens: int = 200) -> str:
        if not self.ok:
            return ""
        import torch
        msgs = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "ФАКТЫ:\n" + facts +
             "\n\nНапиши обоснование гипотезы одним абзацем."},
        ]
        try:
            text = self.tok.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            text = self.tok.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=True)
        inp = self.tok(text, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model.generate(**inp, max_new_tokens=max_new_tokens,
                                      do_sample=False,
                                      pad_token_id=self.tok.eos_token_id)
        return self.tok.decode(out[0][inp.input_ids.shape[1]:],
                               skip_special_tokens=True).strip()


# ----------------------------- Диспетчер -------------------------------------

class LLMReasoner:
    """Единый интерфейс: пробует Yandex, затем локальную модель."""
    _instance = None

    def __init__(self):
        self.backend = None
        self.ok = False
        self.name = None
        self.device = None
        self._err = ""

    def load(self):
        # 1) Yandex AI Studio (основной путь на защите)
        yb = YandexBackend().load()
        if yb.ok:
            self.backend, self.ok = yb, True
            self.name, self.device = yb.name, yb.device
            return self
        # 2) Локальная модель (офлайн-фолбэк)
        lb = LocalBackend().load()
        if lb.ok:
            self.backend, self.ok = lb, True
            self.name, self.device = lb.name, lb.device
            return self
        # 3) Ничего — деградируем к детерминированному тексту
        self._err = f"Yandex: {yb._err}; локально: {lb._err}"
        return self

    def refine(self, facts: str, max_new_tokens: int = 200) -> str:
        if not self.ok or not self.backend:
            return ""
        return self.backend.refine(facts, max_new_tokens=max_new_tokens)


def get_reasoner():
    if LLMReasoner._instance is None:
        LLMReasoner._instance = LLMReasoner().load()
    return LLMReasoner._instance


def facts_block(h, diag) -> str:
    """Готовит компактный блок фактов для LLM из гипотезы и диагноза."""
    lines = [
        f"Объект: {diag.plant}.",
        f"Гипотеза: {h.title}.",
        f"Целевой класс крупности: {h.size_class} мкм.",
        f"Передел: {h.stage}.",
        f"Диагноз-триггер: {h.trigger_finding}.",
        f"Механизм влияния: {h.mechanism}",
        f"Ожидаемый эффект: {h.value_musd:.1f} млн $/год.",
        f"Оборудование: {', '.join(h.equipment)}.",
        f"Критерий успеха: {h.success_criterion}",
    ]
    ev = h.evidence or {}
    if ev:
        lines.append("Опорные числа из данных: " +
                     ", ".join(f"{k}={v}" for k, v in ev.items()) + ".")
    return "\n".join(lines)


def enrich_hypotheses(hyps: list, diag, max_items: int = 5):
    """Дополняет топ-N гипотез LLM-обоснованием (поле llm_rationale).
    Ниже топ-N и при недоступности модели остаётся детерминированное rationale."""
    import time
    r = get_reasoner()
    for i, h in enumerate(hyps[:max_items]):
        txt = r.refine(facts_block(h, diag)) if r.ok else ""
        setattr(h, "llm_rationale", txt)
        if i < max_items - 1:
            time.sleep(0.15)  # мягкий троттлинг под лимит параллельных запросов
    return hyps


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.ingest import parse_tailings_xlsx
    from core.diagnose import diagnose
    from core.generate import generate
    base = os.environ.get('CASE_DIR', 'data/examples')
    rep = parse_tailings_xlsx(f"{base}/Пример 1/Хвосты КГМК.xlsx", "КГМК")
    diag = diagnose(rep)
    hyps = generate(diag)
    r = get_reasoner()
    print("LLM ok:", r.ok, "| backend:", r.name, "| device:", r.device,
          "" if r.ok else f"| причина: {r._err}")
    if r.ok:
        for h in hyps[:2]:
            print(f"\n### {h.title}")
            print("детерм:", h.rationale[:150], "…")
            print("LLM   :", r.refine(facts_block(h, diag)))
