"""
ML classifiers for LedgerLens.

1. Expense categorisation (line items & documents -> accounting category + GL code)
2. Document type detection (invoice / receipt / utility bill / purchase order / credit note)

Both are TF-IDF (word n-grams + character n-grams) + logistic regression pipelines trained at
start-up on a procedurally generated corpus. Evaluation uses a held-out split built from
*different* templates than training, so reported accuracy reflects generalisation rather than
memorisation. Replace the corpus with your own labelled ledger history to specialise it.
"""
from __future__ import annotations

import random
import time

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import FeatureUnion, make_pipeline

CATEGORIES = {
    "Software & Cloud": {"gl": "6100", "color": "#6366f1", "terms": [
        "aws ec2 usage", "aws ec2 instances", "amazon web services usage", "ec2 compute usage", "gcp compute engine usage", "azure vm usage", "azure subscription", "google workspace", "github team plan", "slack pro seats", "zoom licenses", "notion plus", "figma seats", "atlassian jira", 
        "cloud compute instances", "virtual machine hours", "managed database", "postgresql cluster", "object storage",
        "data transfer egress", "saas subscription", "software license", "annual license renewal", "user seats",
        "api usage", "kubernetes cluster", "cdn bandwidth", "serverless functions", "backup storage", "domain renewal",
        "ssl certificate", "premium support plan", "monitoring and logging", "email hosting", "crm subscription",
        "design software seats", "developer tools plan", "load balancer", "container registry", "gpu instances"]},
    "Office Supplies": {"gl": "6200", "color": "#14b8a6", "terms": [
        "copy paper", "printer toner cartridge", "ink cartridges", "whiteboard markers", "sticky notes", "binders",
        "staplers and staples", "desk organizer", "file folders", "envelopes", "notebooks", "ballpoint pens",
        "office chair", "ergonomic chair", "standing desk", "desk lamp", "filing cabinet", "keyboard and mouse",
        "monitor stand", "break room supplies", "cleaning supplies", "paper towels", "label maker tape", "highlighters"]},
    "Marketing & Advertising": {"gl": "6300", "color": "#ec4899", "terms": [
        "paid social campaign", "ad spend", "google ads management", "seo audit", "keyword strategy", "content writing",
        "copywriting", "landing page design", "ad creative production", "brand identity design", "influencer campaign",
        "email marketing campaign", "trade show booth", "printed brochures", "promotional merchandise", "video production",
        "pr outreach", "media buying", "social media management", "marketing retainer", "billboard placement"]},
    "Utilities": {"gl": "6400", "color": "#eab308", "terms": [
        "electricity usage kwh", "natural gas therms", "water and sewer", "demand charge peak kw", "grid connection fee",
        "waste collection", "internet service", "fiber broadband", "business phone lines", "mobile plan", "energy charge",
        "meter service fee", "renewable energy surcharge", "stormwater fee", "heating oil delivery"]},
    "Travel": {"gl": "6500", "color": "#0ea5e9", "terms": [
        "uber ride", "lyft ride", "airbnb stay", "uber trip to client", "delta airlines", "marriott hotel", "amtrak ticket", 
        "return flight economy", "airfare", "hotel nights", "hotel room", "airport transfers", "taxi fare", "rideshare",
        "car rental", "train tickets", "travel insurance", "baggage fee", "seat upgrade", "parking at airport",
        "visa processing fee", "mileage reimbursement", "per diem lodging", "conference travel package"]},
    "Meals & Entertainment": {"gl": "6600", "color": "#f97316", "terms": [
        "doordash order", "starbucks coffee", "grubhub lunch", "cold brew coffee", "iced coffee", "espresso", "cappuccino", "americano", "chai latte", "green tea", "croissant", "bagel", 
        "lunch buffet", "catering service", "coffee and pastries", "oat latte", "cold brew", "avocado toast", "muffin",
        "sparkling water", "team dinner", "client lunch", "breakfast platter", "event staff", "sandwich platter",
        "beverages", "dessert tray", "pizza order", "restaurant bill", "gratuity", "bar tab", "snacks for office"]},
    "Professional Services": {"gl": "6700", "color": "#8b5cf6", "terms": [
        "quarterly bookkeeping", "monthly bookkeeping", "cpa services", "lawyer retainer", 
        "legal consultation", "attorney fees", "accounting services", "bookkeeping", "tax preparation", "audit fees",
        "consulting hours", "strategy workshop", "recruiting fee", "hr consulting", "translation services",
        "notary services", "architecture review", "security penetration test", "software development hours",
        "project management", "training session", "coaching sessions", "due diligence review"]},
    "Equipment & Hardware": {"gl": "6800", "color": "#64748b", "terms": [
        "dell monitor", "apple macbook", "logitech webcam", "lenovo thinkpad", 
        "laptop computer", "macbook pro", "desktop workstation", "27 inch monitor", "docking station", "network switch",
        "wifi access point", "server rack", "external ssd drive", "headsets", "conference room camera", "projector",
        "tablet devices", "printer multifunction", "ups battery backup", "firewall appliance", "graphics card"]},
    "Shipping & Logistics": {"gl": "6900", "color": "#10b981", "terms": [
        "fedex overnight", "ups ground", "dhl express", "usps postage", 
        "ground shipping", "express delivery", "freight charges", "courier service", "pallet transport",
        "customs clearance", "warehouse storage", "packaging materials", "last mile delivery", "fuel surcharge",
        "returns processing", "international shipping", "overnight courier", "fulfillment fees"]},
}


# Compositional vocabulary: descriptive words x item nouns per category. Combined with the curated terms
# above this gives each category a few hundred realistic phrases.
LEXICON = {
    "Software & Cloud": (["cloud", "saas", "software", "server", "compute", "platform", "developer", "analytics",
                          "security", "database", "hosting", "api", "storage", "vm", "kubernetes", "cdn", "backup"],
                         ["license", "subscription", "seats", "instances", "usage", "plan", "credits", "bandwidth",
                          "renewal", "cluster", "egress", "tier", "nodes", "requests", "gb-month"]),
    "Office Supplies": (["office", "desk", "paper", "printer", "stationery", "break room", "copy", "filing",
                         "ergonomic", "writing", "presentation", "mailing"],
                        ["supplies", "chair", "pens", "paper", "toner", "folders", "markers", "notebooks", "organizer",
                         "envelopes", "binders", "cabinet", "lamp", "tape", "labels", "staples"]),
    "Marketing & Advertising": (["marketing", "advertising", "ad", "campaign", "social media", "seo", "brand", "content",
                                 "creative", "email", "pr", "influencer", "media", "promotional", "digital"],
                                ["campaign", "spend", "management", "strategy", "design", "production", "retainer",
                                 "assets", "copywriting", "placement", "audit", "outreach", "merchandise", "video"]),
    "Utilities": (["electricity", "electric", "natural gas", "gas", "water", "sewer", "energy", "power", "internet",
                   "broadband", "phone", "waste", "heating", "grid", "meter"],
                  ["usage", "charge", "service", "fee", "bill", "kwh", "therms", "consumption", "connection",
                   "surcharge", "line rental", "supply", "demand charge"]),
    "Travel": (["flight", "airline", "air", "hotel", "lodging", "train", "rail", "taxi", "rental car", "airport",
                "rideshare", "travel", "baggage", "business class", "economy"],
               ["ticket", "fare", "nights", "room", "transfer", "booking", "insurance", "upgrade", "parking",
                "per diem", "itinerary", "reservation", "mileage"]),
    "Meals & Entertainment": (["lunch", "dinner", "breakfast", "coffee", "catering", "restaurant", "team", "client",
                               "buffet", "pizza", "bakery", "cafe", "beverage", "snack", "event"],
                              ["order", "platter", "service", "meal", "tab", "latte", "pastries", "drinks", "staff",
                               "dessert", "sandwiches", "gratuity", "tasting menu", "appetizers"]),
    "Professional Services": (["legal", "accounting", "consulting", "advisory", "audit", "tax", "recruiting", "hr",
                               "training", "translation", "engineering", "design", "compliance", "strategy"],
                              ["services", "fees", "hours", "retainer", "consultation", "review", "workshop",
                               "engagement", "preparation", "assessment", "sessions", "project", "advice"]),
    "Equipment & Hardware": (["laptop", "computer", "monitor", "network", "server", "storage", "camera", "audio",
                              "printer", "tablet", "workstation", "wifi", "usb-c", "4k", "gaming"],
                             ["hardware", "device", "unit", "switch", "router", "dock", "drive", "headset", "display",
                              "rack", "battery backup", "access point", "projector", "keyboard", "graphics card"]),
    "Shipping & Logistics": (["shipping", "freight", "courier", "delivery", "express", "overnight", "ground",
                              "international", "customs", "warehouse", "pallet", "parcel", "fulfillment", "last mile"],
                             ["charges", "fee", "service", "transport", "clearance", "storage", "surcharge", "label",
                              "handling", "dispatch", "returns", "packaging", "postage"]),
}


def _vocab():
    rng = random.Random(42)
    out = {}
    for cat, spec in CATEGORIES.items():
        attrs, heads = LEXICON[cat]
        combos = [f"{a} {h}" for a in attrs for h in heads if a != h]
        rng.shuffle(combos)
        out[cat] = list(dict.fromkeys(spec["terms"] + combos[:140]))
    return out


MODIFIERS = ["", "", "", "premium", "standard", "monthly", "annual", "business", "pro", "basic", "assorted",
             "q4", "october", "november", "team", "enterprise", "small", "large", "bulk", "deluxe"]
SUFFIXES = ["", "", "", " - October", " (12-pack)", " x2", " per unit", " - monthly", " for HQ", " - Q4",
            " (4 hrs)", " - 1.8 TB", " - tier 2", " ref 2291", " case", " plan"]

DOC_TYPES = {
    "Invoice": ["invoice", "invoice number", "bill to", "due date", "payment terms net 30", "total due", "remit to",
                "purchase order", "amount due", "invoice date", "please pay"],
    "Receipt": ["receipt", "thank you come again", "visa ****", "cash", "change due", "cashier", "transaction",
                "card ending", "store #", "paid", "total"],
    "Utility Bill": ["utility bill", "account number", "service address", "kwh", "meter reading", "billing period",
                     "amount due", "usage", "previous balance", "therms", "statement date"],
    "Purchase Order": ["purchase order", "po number", "ship to", "vendor", "requested by", "deliver by",
                       "authorized signature", "order date", "quantity ordered"],
    "Credit Note": ["credit note", "credit memo", "refund", "original invoice", "credit amount", "adjustment",
                    "returned goods", "amount credited"],
}


def _phrase(rng, term):
    p = term
    m = rng.choice(MODIFIERS)
    if m and rng.random() < 0.6:
        p = f"{m} {p}" if rng.random() < 0.5 else f"{p} {m}"
    p += rng.choice(SUFFIXES)
    if rng.random() < 0.3:
        p = p.title()
    if rng.random() < 0.15:
        p = p.upper()
    if rng.random() < 0.2:  # simulate OCR noise
        i = rng.randrange(len(p))
        p = p[:i] + p[i + 1:]
    return p


def _split_terms(seed=11, holdout=0.25):
    """Hold out ~25% of each category's phrases so evaluation measures generalisation to unseen phrases."""
    rng = random.Random(seed)
    train, test = {}, {}
    for cat, terms in _vocab().items():
        t = terms[:]
        rng.shuffle(t)
        k = max(2, int(len(t) * holdout))
        test[cat], train[cat] = t[:k], t[k:]
    return train, test


def _corpus(seed, vocab, n):
    rng = random.Random(seed)
    X, y = [], []
    for cat, terms in vocab.items():
        for _ in range(n):
            X.append(_phrase(rng, rng.choice(terms)))
            y.append(cat)
    return X, y


def _doc_corpus(seed, n):
    rng = random.Random(seed)
    X, y = [], []
    cats = list(CATEGORIES)
    for dt, cues in DOC_TYPES.items():
        for _ in range(n):
            k = rng.randint(1, 4) if n < 100 else rng.randint(2, 6)
            words = rng.sample(cues, k)
            # content of the document (line items) is not tied to its type
            words += [rng.choice(CATEGORIES[rng.choice(cats)]["terms"]) for _ in range(rng.randint(2, 6))]
            rng.shuffle(words)
            X.append(" ".join(words))
            y.append(dt)
    return X, y


def _pipeline(C=6.0):
    feats = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2)),
    ])
    return make_pipeline(feats, LogisticRegression(C=C, max_iter=2000))


class Classifiers:
    def __init__(self):
        t0 = time.time()
        # 1) honest evaluation: train on 75% of the vocabulary, test on phrases built from unseen terms
        tr_vocab, te_vocab = _split_terms()
        Xtr, ytr = _corpus(1, tr_vocab, 260)
        Xte, yte = _corpus(2, te_vocab, 90)
        pred = _pipeline().fit(Xtr, ytr).predict(Xte)
        self.expense_metrics = {
            "accuracy": round(float(accuracy_score(yte, pred)), 4),
            "macro_f1": round(float(f1_score(yte, pred, average="macro")), 4),
            "n_train": len(Xtr), "n_test": len(Xte), "classes": len(CATEGORIES),
            "eval": "held-out phrases never seen in training",
        }
        # 2) production model is refit on the full vocabulary
        Xall, yall = _corpus(5, _vocab(), 320)
        self.expense = _pipeline().fit(Xall, yall)
        Dtr, dtr = _doc_corpus(3, 220)
        Dte, dte = _doc_corpus(4, 60)
        self.doctype = _pipeline(C=4.0).fit(Dtr, dtr)
        dp = self.doctype.predict(Dte)
        self.doctype_metrics = {
            "accuracy": round(float(accuracy_score(dte, dp)), 4),
            "macro_f1": round(float(f1_score(dte, dp, average="macro")), 4),
            "n_train": len(Dtr), "n_test": len(Dte), "classes": len(DOC_TYPES),
        }
        self.train_seconds = round(time.time() - t0, 2)

    def categorize(self, texts):
        if not texts:
            return []
        proba = self.expense.predict_proba(texts)
        classes = self.expense.classes_
        out = []
        for row in proba:
            i = int(np.argmax(row))
            out.append({"category": str(classes[i]), "confidence": round(float(row[i]), 3),
                        "gl_code": CATEGORIES[classes[i]]["gl"]})
        return out

    def document_category(self, vendor, items):
        """Amount-weighted vote of line-item categories, nudged by the vendor name."""
        classes = list(self.expense.classes_)
        score = np.zeros(len(classes))
        if items:
            texts = [i["description"] for i in items]
            amounts = np.array([max(abs(i.get("amount") or 0), 1) for i in items], float)
            proba = self.expense.predict_proba(texts)
            score += (proba * (amounts / amounts.sum())[:, None]).sum(axis=0)
        if vendor:
            score += 0.35 * self.expense.predict_proba([vendor])[0]
        if score.sum() == 0:
            return None
        score = score / score.sum()
        i = int(np.argmax(score))
        top = sorted(zip(classes, score), key=lambda t: -t[1])[:3]
        return {"category": str(classes[i]), "confidence": round(float(score[i]), 3), "gl_code": CATEGORIES[classes[i]]["gl"],
                "alternatives": [{"category": str(c), "p": round(float(p), 3)} for c, p in top]}

    def document_type(self, text):
        proba = self.doctype.predict_proba([text.lower()[:4000]])[0]
        i = int(np.argmax(proba))
        return {"type": str(self.doctype.classes_[i]), "confidence": round(float(proba[i]), 3)}

    def info(self):
        return {
            "expense_classifier": {**self.expense_metrics, "model": "TF-IDF (word+char n-grams) + Logistic Regression"},
            "doctype_classifier": {**self.doctype_metrics, "model": "TF-IDF (word+char n-grams) + Logistic Regression"},
            "categories": [{"name": k, "gl_code": v["gl"], "color": v["color"]} for k, v in CATEGORIES.items()],
            "train_seconds": self.train_seconds,
        }
