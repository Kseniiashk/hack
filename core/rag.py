"""
RAG-обоснование: поиск релевантных цитат из корпуса учебников для гипотез.

Два режима:
  1) Семантический — sentence-transformers (paraphrase-multilingual-MiniLM,
     лежит в HF-кэше пользователя, работает офлайн). Мультиязычный ru/en/zh.
  2) Fallback — лексический BM25-подобный поиск (чистый Python, без зависимостей),
     если модель/эмбеддинги недоступны. Система деградирует gracefully.

Индекс эмбеддингов кэшируется в data/parsed/emb.npy.
"""
from __future__ import annotations
import os
# До любого импорта transformers: только PyTorch, офлайн (модель в HF-кэше).
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
import json
import math
import re
from collections import Counter


# Частые русские служебные/технические слова — маркер связного текста.
_STOP = set("и в во не что он на я с со как а то все она так его но да ты к у же вы за "
            "бы по только ее мне было вот от меня еще нет о из ему теперь при для до "
            "или если при этом также этих этой этот при руды флотации металла класса "
            "измельчения хвостов минерала процесса которые более менее между через".split())


def _readable(text: str) -> bool:
    """Отсеивает битые OCR-чанки: у связного текста высока доля стоп-слов
    и мало обрывочных 1-2 буквенных фрагментов."""
    toks = re.findall(r"[а-яёa-z]+", text.lower())
    if len(toks) < 12:
        return False
    short = sum(1 for w in toks if len(w) <= 2)
    if short / len(toks) > 0.45:          # много обрывков -> OCR-мусор
        return False
    hits = sum(1 for w in toks if w in _STOP)
    if hits / len(toks) < 0.06:           # связный текст содержит служебные слова
        return False
    # Доля «произносимых» слов: длина 3-16 и без длинных согласных кластеров.
    def ok_word(w):
        if not (3 <= len(w) <= 16):
            return False
        return not re.search(r"[бвгджзйклмнпрстфхцчшщъь]{5,}", w)
    good = sum(1 for w in toks if ok_word(w))
    return good / len(toks) >= 0.5

_DIR = os.path.dirname(__file__)
CORPUS = os.path.join(_DIR, "..", "data", "parsed", "corpus.jsonl")
EMB = os.path.join(_DIR, "..", "data", "parsed", "emb.npy")
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _load_corpus():
    if not os.path.exists(CORPUS):
        return []
    docs = []
    with open(CORPUS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if _readable(d.get("text", "")):
                docs.append(d)
    return docs


def _tok(s):
    return re.findall(r"[а-яёa-z0-9]+", s.lower())


class BM25:
    """Минимальный BM25 без внешних зависимостей — надёжный fallback."""
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = docs
        self.corpus = [_tok(d["text"]) for d in docs]
        self.k1, self.b = k1, b
        self.N = len(self.corpus) or 1
        self.avgdl = sum(len(d) for d in self.corpus) / self.N if self.corpus else 1
        self.df = Counter()
        for d in self.corpus:
            for w in set(d):
                self.df[w] += 1
        self.tf = [Counter(d) for d in self.corpus]

    def _idf(self, w):
        n = self.df.get(w, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def search(self, query, k=2):
        q = _tok(query)
        scores = []
        for i, tf in enumerate(self.tf):
            dl = len(self.corpus[i]) or 1
            s = 0.0
            for w in q:
                if w not in tf:
                    continue
                idf = self._idf(w)
                f = tf[w]
                s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            scores.append((s, i))
        scores.sort(reverse=True)
        out = []
        for s, i in scores[:k]:
            if s <= 0:
                continue
            d = self.docs[i]
            out.append({"source": d["source"], "page": d.get("page"),
                        "snippet": _clip(d["text"]), "score": round(s, 2)})
        return out


def _clip(t, n=300):
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n] + ("…" if len(t) > n else "")


class RAG:
    def __init__(self, prefer_semantic=True):
        self.docs = _load_corpus()
        self.mode = "none"
        self._model = None
        self._emb = None
        self._bm25 = None
        if not self.docs:
            return
        self._bm25 = BM25(self.docs)
        self.mode = "bm25"
        if prefer_semantic:
            self._try_semantic()

    def _try_semantic(self):
        try:
            # Не даём transformers тянуть сломанный TensorFlow/Flax (только PyTorch).
            os.environ.setdefault("USE_TF", "0")
            os.environ.setdefault("USE_FLAX", "0")
            os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            import numpy as np
            from sentence_transformers import SentenceTransformer
            self._np = np
            self._model = SentenceTransformer(MODEL_NAME)
            if os.path.exists(EMB):
                emb = np.load(EMB)
                if emb.shape[0] == len(self.docs):
                    self._emb = emb
            if self._emb is None:
                texts = [d["text"] for d in self.docs]
                self._emb = self._model.encode(
                    texts, batch_size=64, show_progress_bar=False,
                    normalize_embeddings=True)
                np.save(EMB, self._emb)
            self.mode = "semantic"
        except Exception as e:
            self.mode = "bm25"

    def search(self, query, k=2):
        if self.mode == "semantic" and self._emb is not None:
            qv = self._model.encode([query], normalize_embeddings=True)[0]
            sims = self._emb @ qv
            idx = self._np.argsort(-sims)[:k]
            out = []
            for i in idx:
                if sims[i] <= 0.15:
                    continue
                d = self.docs[int(i)]
                out.append({"source": d["source"], "page": d.get("page"),
                            "snippet": _clip(d["text"]),
                            "score": round(float(sims[i]), 3)})
            if out:
                return out
        if self._bm25:
            return self._bm25.search(query, k=k)
        return []


_RAG_SINGLETON = None


def get_rag(prefer_semantic=True):
    global _RAG_SINGLETON
    if _RAG_SINGLETON is None:
        _RAG_SINGLETON = RAG(prefer_semantic=prefer_semantic)
    return _RAG_SINGLETON


if __name__ == "__main__":
    r = get_rag()
    print("mode:", r.mode, "| docs:", len(r.docs))
    for q in ["раскрытие сростков доизмельчение", "флотация тонких классов шламы",
              "гидроциклон классификация крупность"]:
        print(f"\nQ: {q}")
        for c in r.search(q, k=2):
            print(f"  [{c['source']} с.{c.get('page')}] {c['snippet'][:140]}")
