#!/usr/bin/env python3
"""
あるけみすと myshop HTMLパーサー
保存したHTMLからアイテム名と価格を抽出
"""
import re
from pathlib import Path

from myshop_items import (
    CATEGORY_ACCESSORY,
    CATEGORY_ARMOR,
    CATEGORY_FOOT,
    CATEGORY_HEAD,
    CATEGORY_ITEM,
    CATEGORY_WEAPON,
    ITEM_MASTER,
    get_all_items,
)


def _normalize_item_name(name: str) -> tuple[str, int]:
    """
    アイテム名から基本名と強化値を分離
    例: "聖者の杖+4" -> ("聖者の杖", 4)
        "祝福の宝石" -> ("祝福の宝石", 0)
    """
    name = name.strip()
    m = re.match(r"^(.+?)\+(\d+)$", name)
    if m:
        return (m.group(1).strip(), int(m.group(2)))
    return (name, 0)


def _infer_category(item_name: str) -> str | None:
    """アイテム名からカテゴリを推定"""
    for cat, names in ITEM_MASTER.items():
        base = _normalize_item_name(item_name)[0]
        for n in names:
            if base == n or base in n or n in base:
                return cat
    return None


def parse_myshop_html(html: str) -> list[dict]:
    """
    myshop/warehouse/市場 のHTMLからアイテムと価格を抽出
    戻り値: [{"item_name": str, "enhance": int, "price": int, "category": str | None}, ...]
    """
    # 価格パターン: 数字 + マー
    price_pattern = re.compile(r"(\d{1,8})マー")
    results: list[dict] = []
    seen: set[tuple[str, int, int]] = set()

    # アイテム名の候補（全マスターから）
    all_bases = []
    for names in ITEM_MASTER.values():
        all_bases.extend(names)
    all_bases = sorted(set(all_bases), key=len, reverse=True)  # 長い方からマッチ

    # パターン: アイテム名（任意で[X]接頭）+ 数字マー
    # テキストブロックを抽出（タグをスペースに置換）
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    # 各価格の前後の単語からアイテム名を推定
    for m in price_pattern.finditer(text):
        price = int(m.group(1))
        # 価格の前300文字からアイテム名を探す
        start = max(0, m.start() - 300)
        chunk = text[start : m.start()]
        # 最後の長い単語列がアイテム名の可能性が高い
        words = [w for w in chunk.split() if len(w) > 2 and not w.isdigit()]
        if not words:
            continue

        # マスターに含まれる名前を探す
        item_base = None
        enhance = 0
        for base in all_bases:
            # "+数字" の形があれば強化値
            enh_match = re.search(re.escape(base) + r"(?:\+(\d+))?", chunk)
            if enh_match:
                item_base = base
                if enh_match.group(1):
                    enhance = int(enh_match.group(1))
                break
            if base in chunk:
                # +あり
                plus_match = re.search(re.escape(base) + r"\+(\d+)", chunk)
                if plus_match:
                    item_base = base
                    enhance = int(plus_match.group(1))
                    break
                item_base = base
                break

        if item_base is None:
            # マスターにない名前は最後の2-3単語を結合して使う
            candidate = " ".join(words[-2:]) if len(words) >= 2 else words[-1]
            if len(candidate) >= 2 and not candidate.isdigit():
                item_base = candidate
                if re.search(r"\+(\d+)", chunk):
                    em = re.search(r"\+(\d+)", chunk)
                    if em:
                        enhance = int(em.group(1))

        if item_base:
            # 同じ(商品,価格)の重複はパース誤検出の可能性があるためスキップ
            key = (item_base, enhance, price)
            if key not in seen:
                seen.add(key)
                cat = _infer_category(item_base)
                results.append({
                    "item_name": item_base,
                    "enhance": enhance,
                    "price": price,
                    "category": cat,
                })

    return results


def parse_myshop_file(path: str | Path) -> list[dict]:
    """HTMLファイルを読み込んでパース"""
    html = Path(path).read_text(encoding="utf-8")
    return parse_myshop_html(html)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "/Users/masato/Downloads/あるけみすと.html"
    if not Path(path).exists():
        print(f"File not found: {path}")
        sys.exit(1)
    items = parse_myshop_file(path)
    print(f"Parsed {len(items)} items:")
    for i in items:
        enh = f"+{i['enhance']}" if i["enhance"] else ""
        cat = i["category"] or "?"
        print(f"  [{cat}] {i['item_name']}{enh} = {i['price']}マー")
