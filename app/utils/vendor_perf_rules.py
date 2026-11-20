"""Vendor performance ke pure rules (Django ka koi import nahi - seedha test ho sakte hain).

Thresholds yahan badalein; report par laal 'nazar rakhein' flag inhi se banta hai.
"""
MIN_ORDERS = 5          # itne order se kam par rate/speed par flag nahi (kam data se galat nateeja)
CANCEL_WARN_PCT = 20.0  # cancel rate itna ya zyada
MIN_RATINGS = 3         # itni ratings se kam par rating flag nahi
LOW_RATING = 3.5        # isse kam average rating
DISPUTE_WARN = 3        # itne ya zyada disputes
SLOW_DELIVERY_MIN = 90  # order se delivery tak average itne minute ya zyada


def percent(part, whole):
    """Fisad (0-100) ya None agar whole = 0."""
    return round(part * 100.0 / whole, 1) if whole else None


def fmt_minutes(m):
    """67 -> '1h 07m', 25 -> '25m', None -> '-'."""
    if m is None:
        return '-'
    m = int(round(m))
    return f'{m // 60}h {m % 60:02d}m' if m >= 60 else f'{m}m'


def flags(row):
    """Is vendor par nazar rakhne ki wajahon ki list (khali = sab theek)."""
    out = []
    if row.get('orders', 0) >= MIN_ORDERS and row.get('cancel_rate') is not None \
            and row['cancel_rate'] >= CANCEL_WARN_PCT:
        out.append(f"Cancel {row['cancel_rate']:.0f}%")
    if row.get('rating_n', 0) >= MIN_RATINGS and row.get('rating') is not None \
            and row['rating'] < LOW_RATING:
        out.append(f"Rating {row['rating']:.1f}")
    if row.get('disputes', 0) >= DISPUTE_WARN:
        out.append(f"{row['disputes']} disputes")
    if row.get('delivered', 0) >= MIN_ORDERS and row.get('delivery_min') is not None \
            and row['delivery_min'] >= SLOW_DELIVERY_MIN:
        out.append(f"Slow delivery {fmt_minutes(row['delivery_min'])}")
    return out


# ---------------------------------------------------------------------------
# Vendor ka apna performance dashboard (Django ka koi import nahi - seedha test ho sakta hai)
# ---------------------------------------------------------------------------
PREP_GRACE_MIN = 5      # promised prep time se itne minute tak late ho to bhi 'waqt par' maana jata hai
MIN_PREP_SAMPLES = 3    # itne order se kam par prep accuracy ka score/flag nahi

# score ke hisse (jin ka data nahi hota unhe chhod kar baqi ka weighted average liya jata hai)
SCORE_WEIGHTS = {'accept': 35, 'rating': 25, 'prep': 20, 'cancel': 10, 'dispute': 10}


def accept_rate(accepted, rejected, missed):
    """Jin orders par vendor ko jawab dena tha, un mein se kitne accept kiye (0-100) ya None."""
    return percent(accepted, accepted + rejected + missed)


def prep_on_time(promised_min, actual_min, grace=PREP_GRACE_MIN):
    """True = waqt par (ya grace ke andar), False = late, None = data kam."""
    if promised_min is None or actual_min is None:
        return None
    return actual_min <= promised_min + grace


def score_label(score):
    """Score ka lafz aur rang ('good' / 'ok' / 'warn' / 'bad')."""
    if score is None:
        return 'Abhi data kam hai', 'na'
    if score >= 85:
        return 'Zabardast', 'good'
    if score >= 70:
        return 'Achha', 'ok'
    if score >= 50:
        return 'Behtar karein', 'warn'
    return 'Nazar rakhein', 'bad'


def quality_score(m):
    """Store quality score 0-100 ya None (orders MIN_ORDERS se kam hon to None).

    m ki keys: orders, accept_rate, rating, rating_n, prep_on_time_pct, prep_n, cancel_rate, disputes.
    Har hissa 0-100 mein badal kar weights se jorrte hain; jis hisse ka data nahi use shamil nahi karte.
    """
    if not m or m.get('orders', 0) < MIN_ORDERS:
        return None
    parts = {}
    if m.get('accept_rate') is not None:
        parts['accept'] = m['accept_rate']
    if m.get('rating') is not None and m.get('rating_n', 0) >= MIN_RATINGS:
        parts['rating'] = max(0.0, min(100.0, (m['rating'] - 1) * 25.0))   # 1 star = 0, 5 star = 100
    if m.get('prep_on_time_pct') is not None and m.get('prep_n', 0) >= MIN_PREP_SAMPLES:
        parts['prep'] = m['prep_on_time_pct']
    if m.get('cancel_rate') is not None:
        parts['cancel'] = max(0.0, 100.0 - m['cancel_rate'] * 2)            # 50% cancel = 0
    if m['orders']:
        dispute_pct = m.get('disputes', 0) * 100.0 / m['orders']
        parts['dispute'] = max(0.0, 100.0 - dispute_pct * 5)                # 20% disputes = 0
    if not parts:
        return None
    total_w = sum(SCORE_WEIGHTS[k] for k in parts)
    return int(round(sum(parts[k] * SCORE_WEIGHTS[k] for k in parts) / total_w))


def delta(now_value, before_value):
    """Pichhli muddat se farq (number) ya None agar dono mein se koi na ho."""
    if now_value is None or before_value is None:
        return None
    return round(now_value - before_value, 1)


def tips(m):
    """Vendor ke liye seedhe, amali mashware (khali list = sab theek)."""
    out = []
    if not m or m.get('orders', 0) < MIN_ORDERS:
        return out
    if m.get('missed', 0) > 0:
        out.append(f"{m['missed']} order ka jawab waqt par nahi diya gaya. Phone ki awaaz/notification on rakhein "
                   f"aur busy hon to Busy mode ya Auto-accept use karein.")
    if m.get('accept_rate') is not None and m['accept_rate'] < 90 and m.get('rejected', 0) > 0:
        out.append(f"{m['rejected']} order reject hue. Jo item khatam ho use menu mein off kar dein, taake customer "
                   f"wo order kare hi nahi.")
    if m.get('prep_on_time_pct') is not None and m.get('prep_n', 0) >= MIN_PREP_SAMPLES \
            and m['prep_on_time_pct'] < 80:
        out.append("Aap jitna prep time batate hain, order usse late ready hota hai. Accept karte waqt thora "
                   "zyada (sahi) waqt likhein.")
    if m.get('cancel_rate') is not None and m['cancel_rate'] >= CANCEL_WARN_PCT:
        out.append(f"Cancel rate {m['cancel_rate']:.0f}% hai. Cancel ki wajah dekhein aur menu/timings theek rakhein.")
    if m.get('rating') is not None and m.get('rating_n', 0) >= MIN_RATINGS and m['rating'] < LOW_RATING:
        out.append(f"Average rating {m['rating']:.1f} hai. Reviews mein shikayat dekh kar jawab dein aur masla theek karein.")
    if m.get('disputes', 0) >= DISPUTE_WARN:
        out.append(f"{m['disputes']} disputes aaye. Disputes page par jawab dein.")
    return out
