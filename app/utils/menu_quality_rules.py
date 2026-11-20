"""Menu quality ke pure rules (Django ka koi import nahi - seedha test ho sakte hain).

Har item 100 number ka: photo 40 + description 35 + naam 25.
Menu score = saare items ka average; 'complete' item = jis ke teeno hisse poore hon.
Thresholds / weights yahan badalein.
"""
W_PHOTO, W_DESC, W_NAME = 40, 35, 25
MIN_DESC = 20            # itne harf se chhota description 'kam' mana jata hai
MIN_NAME, MAX_NAME = 4, 60
GOOD, FAIR = 80, 50      # score >= GOOD: achha, >= FAIR: theek, warna kamzor

ISSUE_TEXT = {
    'photo': 'Add a photo',
    'desc': f'Write a description (at least {MIN_DESC} characters)',
    'name': 'Fix the name (4-60 characters, not ALL CAPS)',
}
JUNK_NAMES = {'test', 'item', 'product', 'demo', 'abc', 'xyz', 'asdf'}


def name_ok(name):
    text = (name or '').strip()
    if not (MIN_NAME <= len(text) <= MAX_NAME):
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    if text.lower() in JUNK_NAMES:
        return False
    if len(letters) >= 4 and all(c.isupper() for c in letters):    # SHOUTING NAAM
        return False
    return True


def item_check(name, description, has_photo):
    """-> {'score': 0-100, 'issues': ['photo', 'desc', 'name'] (jo kam hain)}"""
    issues, score = [], 0
    if has_photo:
        score += W_PHOTO
    else:
        issues.append('photo')
    if len((description or '').strip()) >= MIN_DESC:
        score += W_DESC
    else:
        issues.append('desc')
    if name_ok(name):
        score += W_NAME
    else:
        issues.append('name')
    return {'score': score, 'issues': issues}


def label(score):
    """-> (text, tone)"""
    if score >= GOOD:
        return 'Good', 'good'
    if score >= FAIR:
        return 'Fair', 'warn'
    return 'Needs work', 'bad'


def summarize(rows):
    """rows = item_check() ke dicts. -> score (0-100, None agar koi item nahi), complete_pct, counts."""
    n = len(rows)
    if not n:
        return {'items': 0, 'score': None, 'complete': 0, 'complete_pct': None,
                'missing_photo': 0, 'missing_desc': 0, 'bad_name': 0}
    complete = sum(1 for r in rows if not r['issues'])
    return {
        'items': n,
        'score': round(sum(r['score'] for r in rows) / n),
        'complete': complete,
        'complete_pct': round(complete * 100.0 / n),
        'missing_photo': sum(1 for r in rows if 'photo' in r['issues']),
        'missing_desc': sum(1 for r in rows if 'desc' in r['issues']),
        'bad_name': sum(1 for r in rows if 'name' in r['issues']),
    }
