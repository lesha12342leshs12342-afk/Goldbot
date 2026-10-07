"""Gold Signals (Android APK, Kivy). Логика на чистом Python, без numpy/pandas.
Не является финансовой рекомендацией."""
import html, json, math, re, ssl, threading, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

SYMBOL = "GC=F"
# имя: (интервал, период, группировка в секундах, вес)
TFS = {"15m": ("15m", "30d", None, 1), "1h": ("1h", "60d", None, 2),
       "4h": ("1h", "180d", 14400, 3), "1d": ("1d", "2y", None, 3)}
TTL = {"15m": 30, "1h": 60, "4h": 60, "1d": 300}
NEWS_URL = ("https://news.google.com/rss/search?q=gold+price+OR+Fed+OR+inflation"
            "+OR+%22safe+haven%22&hl=en-US&gl=US&ceid=US:en")
FC_URL = ("https://news.google.com/rss/search?q=gold+price+forecast+target+OR+outlook+Goldman+OR+JPMorgan"
          "+OR+UBS+OR+Citi+OR+HSBC+OR+%22Morgan+Stanley%22+OR+Commerzbank+OR+ANZ+when:7d&hl=en-US&gl=US&ceid=US:en")
BULL = ["rally", "surge", "record high", "safe haven", "rate cut", "dovish", "weaker dollar", "weak dollar",
        "geopolitical", "tensions", "gains", "rises", "jumps", "climbs", "soars", "haven demand",
        "central bank buying", "inflation fears", "war"]
BEAR = ["falls", "drops", "slump", "rate hike", "hawkish", "stronger dollar", "strong dollar", "yields rise",
        "selloff", "sell-off", "slides", "declines", "lower", "pressure", "profit-taking", "retreats",
        "tumbles", "ceasefire", "risk-on"]
HIGH = re.compile(r"\b(fed|powell|fomc|cpi|payrolls?|nfp|rate decision|war|strike|missile|sanctions?|tariffs?|attack|emergency|breaking)\b")
BANKS = ["Goldman", "JPMorgan", "UBS", "Citi", "Bank of America", "BofA", "HSBC", "Morgan Stanley",
         "Commerzbank", "ANZ", "Deutsche", "Barclays", "Standard Chartered", "Macquarie", "Wells Fargo"]


# ---------- утилиты ----------
def clip(x, a=-1.0, b=1.0): return max(a, min(b, x))
def mean(x): return sum(x) / len(x) if x else 0.0
def std(x):
    m = mean(x); return math.sqrt(sum((v - m) ** 2 for v in x) / len(x))

try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CTX = None

def http(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        return urllib.request.urlopen(req, timeout=20, context=_CTX).read()
    except Exception as e:
        if "CERTIFICATE" in str(e).upper():
            return urllib.request.urlopen(req, timeout=20, context=ssl._create_unverified_context()).read()
        raise

def load(sym, interval, rng, step=None):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(sym)}?interval={interval}&range={rng}")
    r = json.loads(http(url))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    rows = [(t, o, h, l, c) for t, o, h, l, c in
            zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]) if None not in (o, h, l, c)]
    if step:
        g, order = {}, []
        for t, o, h, l, c in rows:
            k = int(t // step)
            if k not in g: g[k] = [o, h, l, c]; order.append(k)
            else: x = g[k]; x[1] = max(x[1], h); x[2] = min(x[2], l); x[3] = c
        return tuple(list(v) for v in zip(*[g[k] for k in order]))
    return tuple(list(v) for v in zip(*[(o, h, l, c) for _, o, h, l, c in rows]))


# ---------- индикаторы ----------
def ewm(x, a):
    out = [x[0]]
    for v in x[1:]: out.append(a * v + (1 - a) * out[-1])
    return out

def ema(x, n): return ewm(x, 2 / (n + 1))

def rsi(c, n=14):
    d = [c[i] - c[i - 1] for i in range(1, len(c))]
    up, dn = ewm([max(v, 0) for v in d], 1 / n)[-1], ewm([max(-v, 0) for v in d], 1 / n)[-1]
    return 100 - 100 / (1 + up / max(dn, 1e-12))

def trs(h, l, c): return [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
def atr(h, l, c, n=14): return ewm(trs(h, l, c), 1 / n)[-1]

def candle(o, h, l, c):
    O, H, L, C, PO, PC = o[-1], h[-1], l[-1], c[-1], o[-2], c[-2]
    body, rng = abs(C - O), max(H - L, 1e-9)
    lo, up = min(O, C) - L, H - max(O, C)
    if PC < PO and C > O and C >= PO and O <= PC: return 1, "бычье поглощение"
    if PC > PO and C < O and C <= PO and O >= PC: return -1, "медвежье поглощение"
    if lo > 2 * body and up < body and body / rng < .35: return 1, "молот"
    if up > 2 * body and lo < body and body / rng < .35: return -1, "падающая звезда"
    if body / rng < .1: return 0, "доджи"
    return 0, ""

def analyze(o, h, l, c):
    s, why = 0.0, []
    e20, e50, e200 = ema(c, 20)[-1], ema(c, 50)[-1], ema(c, 200)[-1]
    if c[-1] > e50 > e200: s += 2; why.append("тренд вверх")
    elif c[-1] < e50 < e200: s -= 2; why.append("тренд вниз")
    s += 1 if e20 > e50 else -1
    macd = [a - b for a, b in zip(ema(c, 12), ema(c, 26))]
    hist = [a - b for a, b in zip(macd, ema(macd, 9))]
    if hist[-1] > 0 and hist[-1] > hist[-2]: s += 1; why.append("MACD растёт")
    elif hist[-1] < 0 and hist[-1] < hist[-2]: s -= 1; why.append("MACD падает")
    r = rsi(c)
    if r < 30: s += 1; why.append(f"RSI {r:.0f} перепродан")
    elif r > 70: s -= 1; why.append(f"RSI {r:.0f} перекуплен")
    w = c[-20:]; ma, sd = mean(w), std(w)
    if c[-1] < ma - 2 * sd: s += 1; why.append("ниже полосы Боллинджера")
    elif c[-1] > ma + 2 * sd: s -= 1; why.append("выше полосы Боллинджера")
    ks = []
    for i in (1, 2, 3):
        lo_, hi_ = min(l[-i - 13:len(l) - i + 1]), max(h[-i - 13:len(h) - i + 1])
        ks.append(100 * (c[-i] - lo_) / max(hi_ - lo_, 1e-9))
    k, d = ks[0], mean(ks)
    if k < 20 and k > d: s += 1; why.append("стохастик вверх")
    elif k > 80 and k < d: s -= 1; why.append("стохастик вниз")
    n = 14
    pdm = [max(h[i] - h[i - 1], 0) if (h[i] - h[i - 1]) > (l[i - 1] - l[i]) else 0 for i in range(1, len(h))]
    mdm = [max(l[i - 1] - l[i], 0) if (l[i - 1] - l[i]) > (h[i] - h[i - 1]) else 0 for i in range(1, len(h))]
    at = [max(v, 1e-9) for v in ewm(trs(h, l, c), 1 / n)]
    pdi = [100 * a / b for a, b in zip(ewm(pdm, 1 / n), at)]
    mdi = [100 * a / b for a, b in zip(ewm(mdm, 1 / n), at)]
    adx = ewm([100 * abs(a - b) / max(a + b, 1e-9) for a, b in zip(pdi, mdi)], 1 / n)[-1]
    if adx > 25:
        up_ = pdi[-1] > mdi[-1]; s += 1 if up_ else -1
        why.append(f"ADX {adx:.0f}: сильный тренд {'вверх' if up_ else 'вниз'}")
    tp = [(h[i] + l[i] + c[i]) / 3 for i in range(-20, 0)]
    m_ = mean(tp); cci = (tp[-1] - m_) / max(.015 * mean([abs(v - m_) for v in tp]), 1e-9)
    if cci < -100: s += 1; why.append(f"CCI {cci:.0f} перепродан")
    elif cci > 100: s -= 1; why.append(f"CCI {cci:.0f} перекуплен")
    cs, name = candle(o, h, l, c)
    s += cs
    if name: why.append(f"свеча: {name}")
    return clip(s / 10), why, atr(h, l, c)


# ---------- новости, прогнозы, макро ----------
def _tag(x, t):
    m = re.search("<" + t + ">(.*?)</" + t + ">", x, re.S)
    if not m: return ""
    v = m.group(1).strip()
    if v.startswith("<![CDATA["): v = v[9:-3]
    return html.unescape(v)

def rss(url, limit=40):
    out, now = [], datetime.now(timezone.utc)
    for it in re.findall(r"<item>(.*?)</item>", http(url).decode("utf-8", "ignore"), re.S)[:limit]:
        try: age = (now - parsedate_to_datetime(_tag(it, "pubDate"))).total_seconds() / 60
        except Exception: age = 9999
        out.append((_tag(it, "title"), age))
    return out

def news_sentiment(limit=25):
    try: titles = [t for t, _ in rss(NEWS_URL, limit)]
    except Exception as e: return 0.0, [f"новости недоступны: {e}"]
    tot, shown = 0.0, []
    for n, t in enumerate(titles):
        tl = t.lower()
        s = sum(w in tl for w in BULL) - sum(w in tl for w in BEAR)
        tot += clip(s, -2, 2) * (1 - n / (2 * max(len(titles), 1)))
        if s and len(shown) < 5: shown.append(("+ " if s > 0 else "- ") + t[:85])
    return clip(tot / max(len(titles), 1) * 2), shown

def forecasts(titles, price):
    """Прогнозы банков из заголовков: целевые цены и тон."""
    sc, lines = [], []
    for t, _ in titles:
        tl = t.lower()
        bank = next((b for b in BANKS if b.lower() in tl), None)
        nums = [float(x.replace(",", "")) for x in re.findall(r"\$\s?(\d{1,2},?\d{3})(?!\d)", t)]
        nums = [n for n in nums if .6 * price < n < 1.8 * price]
        if nums: v = clip((nums[0] / price - 1) * 8)
        else:
            v = (any(w in tl for w in ("bullish", "upside", "raises", "higher", "surge"))
                 - any(w in tl for w in ("bearish", "downside", "cuts", "lower", "slump"))) * .5
        if (bank or nums) and v:
            sc.append(v)
            if bank and len(lines) < 6:
                lines.append(f"{bank}: " + (f"цель {nums[0]:.0f}, " if nums else "") + ("бычий" if v > 0 else "медвежий"))
    return (clip(mean(sc)) if sc else 0.0), list(dict.fromkeys(lines))

def macro_score():
    s, why = 0.0, []
    for sym, name, sg, th in (("DX-Y.NYB", "индекс доллара", -1, .005), ("^TNX", "доходность 10Y", -1, .005),
                              ("^VIX", "VIX (страх)", 1, .05)):
        try:
            c = load(sym, "1d", "1mo")[3]
            ch = c[-1] / c[-5] - 1
            if abs(ch) > th:
                d = sg * (1 if ch > 0 else -1) * .4
                s += d
                why.append(f"{name} {'растёт' if ch > 0 else 'падает'}: {'плюс' if d > 0 else 'минус'} для золота")
        except Exception:
            pass
    return clip(s), why


# ---------- кэш, живая цена, уровни, риск скачка ----------
CACHE, LAST = {}, {"p": None}

def cached(key, ttl, fn):
    t, v = CACHE.get(key, (0, None))
    if v is None or time.time() - t > ttl:
        try: v = fn()
        except Exception:
            if v is None: raise
        CACHE[key] = (time.time(), v)
    return v

def live_price():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(SYMBOL) + "?interval=1m&range=1d"
    return float(json.loads(http(url))["chart"]["result"][0]["meta"]["regularMarketPrice"])

def levels(price, a):
    """Пивоты по вчерашнему дню: цена у поддержки (+) или сопротивления (-)."""
    h, l, c = cached("1d", TTL["1d"], lambda: load(SYMBOL, "1d", "2y", None))[1:]
    H, L, C = h[-2], l[-2], c[-2]
    P = (H + L + C) / 3
    lv = {"S2": P - (H - L), "S1": 2 * P - H, "P": P, "R1": 2 * P - L, "R2": P + H - L}
    a = a or price * .002
    sc = sum((.6 if k[0] == "S" else -.6 if k[0] == "R" else 0) for k, v in lv.items() if abs(price - v) < .6 * a)
    return clip(sc), "  ".join(f"{k} {v:.0f}" for k, v in lv.items())

def sharp(p, fresh):
    """Риск резкого движения в ближайшие минуты: волатильность, squeeze, импульс, новости."""
    o, h, l, c = cached("1m", 15, lambda: load(SYMBOL, "1m", "1d"))
    h, l, c = h[-120:], l[-120:], c[-120:]
    if len(c) < 70: return 0.0, 0, ["мало минутных данных (рынок закрыт?)"]
    if p: c[-1] = p; h[-1] = max(h[-1], p); l[-1] = min(l[-1], p)
    af, asl = atr(h, l, c, 5), max(atr(h, l, c, 60), 1e-9)
    risk, why, d = 0.0, [], 0
    if af / asl > 1.6: risk += .3; why.append(f"волатильность x{af / asl:.1f} от нормы")
    bw = [std(c[i - 20:i]) for i in range(20, len(c) + 1)]
    if bw[-1] <= sorted(bw)[int(.15 * len(bw))]: risk += .25; why.append("сжатие (squeeze): близок пробой")
    mv = (c[-1] - c[-6]) / asl
    if abs(mv) > 2: risk += .3; d = 1 if mv > 0 else -1; why.append(f"импульс {mv:+.1f} ATR за 5 мин")
    if fresh: risk += .3; why.append("важная новость: " + fresh[:60])
    return min(risk, 1.0), d, why


# ---------- главный расчёт ----------
def compute(pos=0, entry=None):
    try: p = live_price()
    except Exception: p = None
    lines, tech, wsum, price, a1 = [], 0.0, 0, None, None
    for name, (iv, per, step, w) in TFS.items():
        try:
            o, h, l, c = cached(name, TTL[name], lambda iv=iv, per=per, step=step: load(SYMBOL, iv, per, step))
            o, h, l, c = o[-400:], h[-400:], l[-400:], c[-400:]
            if p: c[-1] = p; h[-1] = max(h[-1], p); l[-1] = min(l[-1], p)
            sc, why, a = analyze(o, h, l, c)
        except Exception as e:
            lines.append(f"[{name}] ошибка: {e}"); continue
        tech += sc * w; wsum += w; price = float(c[-1])
        if name == "1h": a1 = a
        lines.append(f"[{name}] {sc:+.2f}: " + "; ".join(why[:5]))
    if not wsum: return "НЕТ ДАННЫХ", "\n".join(lines), False
    LAST["p"], tech = price, tech / wsum
    news, heads = cached("news", 300, news_sentiment)
    macro, mwhy = cached("macro", 300, macro_score)
    fc, fclines = forecasts(cached("fc", 600, lambda: rss(FC_URL)), price)
    lv, lvtxt = levels(price, a1)
    fresh = next((t for t, age in cached("newsraw", 120, lambda: rss(NEWS_URL)) if age <= 30 and HIGH.search(t.lower())), "")
    try: risk, rdir, rwhy = sharp(p, fresh)
    except Exception: risk, rdir, rwhy = 0.0, 0, ["минутные данные недоступны"]
    tot = .5 * tech + .15 * news + .15 * fc + .1 * macro + .1 * lv
    sig = ("СИЛЬНАЯ ПОКУПКА" if tot >= .5 else "ПОКУПКА" if tot >= .25 else
           "СИЛЬНАЯ ПРОДАЖА" if tot <= -.5 else "ПРОДАЖА" if tot <= -.25 else "ЖДАТЬ")
    head, alert, adv = sig, False, ""
    if pos:
        nm = "ЛОНГ" if pos > 0 else "ШОРТ"
        stop = take = None
        if a1 and entry: stop, take = entry - pos * 1.5 * a1, entry + pos * 3 * a1
        why = None
        if stop and (price - stop) * pos <= 0: why = "сработал стоп"
        elif take and (price - take) * pos >= 0: why = "цель достигнута, фиксируйте прибыль"
        elif tot * pos <= -.25: why = "сигнал развернулся против позиции"
        elif risk >= .5 and rdir != pos:
            why = "ожидается резкое движение ПРОТИВ вас" if rdir == -pos else "ожидается резкий скачок, направление неясно"
        if why: head, alert, adv = f"ЗАКРЫТЬ {nm}!", True, why
        else:
            head = f"ДЕРЖАТЬ {nm}"
            adv = "резкое движение в вашу сторону: подтяните стоп" if risk >= .5 else "условия для удержания"
        if entry: adv += f"\nВход {entry:.2f}, P&L {(price - entry) * pos:+.2f}"
    elif risk >= .5:
        adv = "ВНИМАНИЕ: высокий риск скачка, вход опасен"
    out = [adv, f"Цена {price:.2f} | Итог {tot:+.2f} | Рынок: {sig}",
           f"Техника {tech:+.2f} Новости {news:+.2f} Прогнозы {fc:+.2f} Макро {macro:+.2f} Уровни {lv:+.2f}", "",
           f"Риск резкого движения: {risk:.0%}"] + ["  - " + w for w in rwhy] + [""] + lines
    out += ["", "Пивоты: " + lvtxt]
    if a1 and abs(tot) >= .25 and not pos:
        d = 1 if tot > 0 else -1
        out.append(f"Стоп {price - d * 1.5 * a1:.2f}  Тейк {price + d * 3 * a1:.2f} (ATR 1h)")
    out += ["", "Прогнозы банков (из заголовков):"] + (fclines or ["не найдено"])
    out += ["", "Новости:"] + heads + ["", "Макро:"] + mwhy
    out += ["", "Не финансовая рекомендация. Риск потери капитала."]
    return head, "\n".join(out), alert


# ---------- интерфейс Kivy ----------
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

BG = (.07, .07, .09, 1)


def head_color(h):
    if "ЗАКРЫТЬ" in h or "ПРОДАЖА" in h: return (1, .35, .3, 1)
    if "ПОКУПКА" in h: return (.3, .9, .45, 1)
    if "ДЕРЖАТЬ" in h: return (.5, .8, 1, 1)
    return (.85, .85, .85, 1)


class GoldApp(App):
    def build(self):
        self.title = "Gold Signals"
        Window.clearcolor = BG
        root = BoxLayout(orientation="vertical", padding=12, spacing=10)
        self.sig = Label(text="Загрузка (20-30 сек)...", font_size="24sp", bold=True,
                         size_hint_y=None, height=90, halign="center")
        sv = ScrollView()
        self.det = Label(text="", size_hint_y=None, halign="left", valign="top", font_size="14sp")
        self.det.bind(width=lambda *_: setattr(self.det, "text_size", (self.det.width - 10, None)),
                      texture_size=lambda *_: setattr(self.det, "height", self.det.texture_size[1]))
        sv.add_widget(self.det)
        row = BoxLayout(size_hint_y=None, height=56, spacing=8)
        self.pbtn = Button(text="Позиция: НЕТ", on_release=self.cycle)
        self.btn = Button(text="Пауза", on_release=self.toggle)
        row.add_widget(self.pbtn); row.add_widget(self.btn)
        root.add_widget(self.sig); root.add_widget(sv); root.add_widget(row)
        self.running = self.alive = True
        self.position, self.entry = 0, None
        threading.Thread(target=self._loop, daemon=True).start()
        return root

    def cycle(self, *_):  # НЕТ -> LONG -> SHORT -> НЕТ, цена входа = текущая
        self.position = {0: 1, 1: -1, -1: 0}[self.position]
        self.entry = LAST["p"] if self.position else None
        self.pbtn.text = "Позиция: " + {0: "НЕТ", 1: "LONG", -1: "SHORT"}[self.position]

    def toggle(self, *_):
        self.running = not self.running
        self.btn.text = "Пауза" if self.running else "Продолжить"

    def on_pause(self):
        return True

    def on_stop(self):
        self.alive = False

    def _loop(self):
        while self.alive:
            t0, delay = time.time(), 1.0
            if self.running:
                if self.position and self.entry is None and LAST["p"]:
                    self.entry = LAST["p"]
                try:
                    res = compute(self.position, self.entry)
                except Exception as e:
                    res, delay = ("ОШИБКА", str(e), False), 5.0
                Clock.schedule_once(lambda dt, r=res: self._show(*r))
            time.sleep(max(0.05, delay - (time.time() - t0)))

    def _show(self, head, text, alert):
        self.sig.text, self.sig.color, self.det.text = head, head_color(head), text
        Window.clearcolor = (.35, .05, .05, 1) if alert else BG


if __name__ == "__main__":
    GoldApp().run()
