"""Customer shop home: category ke naam se icon (Step 9 polish).

Usage: {% load shop_ui %} ... <i class="bi {{ cat.name|cat_icon:forloop.counter0 }}"></i>
Naam mein keyword mile to uska icon; warna purana rotating icon (koi category khali icon nahi rehti).
"""
import re

from django import template

register = template.Library()

# (keywords, bootstrap-icon). Pehla match jeet-ta hai, is liye specific cheezein pehle.
ICONS = (
    (('juice', 'drink', 'beverage', 'cola', 'soda', 'shake', 'sharbat', 'water'), 'bi-cup-straw'),
    (('tea', 'coffee', 'chai'), 'bi-cup-hot-fill'),
    (('milk', 'dairy', 'yogurt', 'yoghurt', 'curd', 'butter', 'cheese', 'ghee'), 'bi-droplet-half'),
    (('egg',), 'bi-egg-fried'),
    (('fruit',), 'bi-apple'),
    (('vegetable', 'veggie', 'sabzi'), 'bi-flower2'),
    (('bakery', 'bread', 'cake', 'biscuit', 'cookie', 'dessert', 'sweet', 'mithai'), 'bi-cake2-fill'),
    (('snack', 'chips', 'chocolate', 'candy', 'namkeen'), 'bi-bag-heart-fill'),
    (('meat', 'chicken', 'beef', 'mutton', 'fish', 'frozen'), 'bi-snow2'),
    (('grocery', 'rice', 'flour', 'atta', 'oil', 'spice', 'masala', 'pulse', 'daal', 'dal', 'sugar', 'ration'), 'bi-basket2-fill'),
    (('medicine', 'pharma', 'health', 'vitamin'), 'bi-capsule-pill'),
    (('beauty', 'cosmetic', 'personal', 'soap', 'shampoo', 'skin'), 'bi-flower1'),
    (('baby', 'kid', 'toy'), 'bi-balloon-heart-fill'),
    (('mobile', 'phone', 'electronic', 'gadget', 'accessor', 'charger'), 'bi-phone-fill'),
    (('home', 'kitchen', 'house', 'clean', 'detergent', 'household', 'laundry'), 'bi-house-heart-fill'),
    (('pet',), 'bi-heart-fill'),
    (('stationery', 'book', 'office'), 'bi-journal-text'),
)
FALLBACK = ('bi-basket2-fill', 'bi-cup-hot-fill', 'bi-bag-heart-fill', 'bi-capsule-pill',
            'bi-flower1', 'bi-phone-fill', 'bi-house-heart-fill')


@register.filter
def cat_icon(name, index=0):
    n = (name or '').lower()
    for words, icon in ICONS:
        if any(re.search(r'\b' + w, n) for w in words):   # shabd ke shuru se (steak != tea)
            return icon
    try:
        return FALLBACK[int(index) % len(FALLBACK)]
    except (TypeError, ValueError):
        return FALLBACK[0]
