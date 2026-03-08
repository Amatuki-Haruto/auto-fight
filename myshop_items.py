#!/usr/bin/env python3
"""
あるけみすと myshop アイテムマスター
https://games-alchemist.com/myshop/ で取り扱われる全アイテム一覧
出典: https://wikiwiki.jp/alchemist-p/装備
"""

# カテゴリ定義（myshopの分類）
CATEGORY_WEAPON = "武器"
CATEGORY_HEAD = "頭具"
CATEGORY_ARMOR = "防具"
CATEGORY_FOOT = "足具"
CATEGORY_ACCESSORY = "アクセサリー"
CATEGORY_ITEM = "アイテム"

# 武器（武器種）
WEAPONS = [
    "こんぼう", "アイアンブレード", "ウッドハンマー", "アイアンバックラー",  # F
    "ブロンズスピア", "シルバーダガー", "アイアンモーニングスター", "紅蓮の盾",  # E
    "スチールソード", "オークウォーハンマー", "ブロンズピケ", "竜皮の盾",  # D
    "ミスリルブレード", "エレガントラピア", "ステンレスクロウ", "サンライトシールド",  # C
    "虚空を断つ刀", "シルバーナイトソード", "ドラゴンバトルハンマー",  # B
    "ミスリルステッキ", "聖騎士の刃楯", "天啓目録",
    "オニキスブレード", "デーモンズグレイブ", "聖者の杖", "アヴァロンの盾",  # A
    "クリムゾンバレット",
    "絶対零弩", "夢幻水晶", "ヴァルキリーシールド", "引鉄斧", "聖槍ロンギヌス",  # S
]

# 頭具
HEADGEAR = [
    "ベレー帽", "赤いリボン",  # F
    "てっかめん", "シルバーイヤリング",  # E
    "ドラゴンヘルム", "ホワイトブリム",  # D
    "カウボーイハット", "天使の光輪",  # C
    "戦士のバンダナ", "モコモコマフラー",  # B
    "アルケ・ゴーグル", "フレイムクラウン",  # A
    "ルナ・ティアラ", "タイタンヘッド",  # S
]

# 防具
ARMOR = [
    "くさりかたびら", "布のローブ",  # F
    "鋼鉄の鎧", "魔法使いのローブ",  # E
    "ドラゴンスキンアーマー", "エルフのシルクローブ",  # D
    "守護者の鎧", "賢者のローブ",  # C
    "デーモンプレートアーマー", "幻影のローブ",  # B
    "光の鎧", "大魔導師のローブ",  # A
    "厄災のヴェール", "煉獄の炎鎧",  # S
]

# 足具
FOOTWEAR = [
    "レザーブーツ", "布製のブーツ",  # F
    "鉄のブーツ", "エナメルブーツ",  # E
    "鋼鉄のブーツ", "クロコダイルブーツ",  # D
    "神秘のブーツ", "砂漠のブーツ",  # C
    "フォレストブーツ", "竜鱗のブーツ",  # B
    "星空ブーツ", "シャドウブーツ",  # A
    "雷鳴のグリーブス", "クロノギア・ブーツ",  # S
]

# アクセサリー
ACCESSORIES = [
    "銅の指輪", "布製のベルト",  # F
    "銀のペンダント", "鋼鉄の腕輪",  # E
    "ルビーの指輪", "魔法のネックレス",  # D
    "竜の牙", "宝石のブローチ",  # C
    "伝説のメダリオン", "星屑のリング",  # B
    "神秘のペンダント", "太陽のアミュレット",  # A
    "竜王のブレスレット", "ミスティック・オーブ",  # S
]

# アイテム（タネ・祝福など - myshopで販売される非装備品）
# 出典: 農場(種)、装備(祝福・霊魂・神託)
ITEMS = [
    # タネ（農場で使用、手相変更）
    "生命の種", "魔力の種", "力の種", "命中の種",
    "耐久の種", "知識の種", "素早さの種", "幸運の種",
    "衰弱の種", "魔弱の種", "非力の種", "失中の種",
    "弱体の種", "無知の種", "鈍足の種", "不幸の種",
    "やりなおしの種",
    # 祝福・宝石系
    "祝福の宝石",
    "霊魂の宝石",
    "神託の羽ペン",
]

# 強化値について:
# 装備は合成で+1,+2,...と強化できる。同じ強化値の装備3つ→1つ上のランク。
# 成功:+1 / 大成功:+2 / 超成功:+3
# 換算: +1≒ノーマル3個分、+2≒9個分、+3≒27個分 (3^n)
# 例外: 祝福の宝石での強化、霊魂の宝石での固定など


def format_item_with_enhance(base_name: str, enhance: int) -> str:
    """強化値を付けた表示名。enhance=0ならそのまま"""
    if enhance <= 0:
        return base_name
    return f"{base_name}+{enhance}"

# 全アイテムをカテゴリ別にまとめたマスター
ITEM_MASTER: dict[str, list[str]] = {
    CATEGORY_WEAPON: WEAPONS,
    CATEGORY_HEAD: HEADGEAR,
    CATEGORY_ARMOR: ARMOR,
    CATEGORY_FOOT: FOOTWEAR,
    CATEGORY_ACCESSORY: ACCESSORIES,
    CATEGORY_ITEM: ITEMS,
}


def get_all_items() -> list[tuple[str, str]]:
    """(category, item_name) のリストを返す"""
    result: list[tuple[str, str]] = []
    for cat, names in ITEM_MASTER.items():
        for name in names:
            result.append((cat, name))
    return result


def get_items_by_category(category: str) -> list[str]:
    """カテゴリ名でアイテムリストを取得"""
    return ITEM_MASTER.get(category, [])


def get_categories() -> list[str]:
    """全カテゴリ名リスト"""
    return list(ITEM_MASTER.keys())


if __name__ == "__main__":
    for cat in get_categories():
        items = get_items_by_category(cat)
        print(f"\n## {cat} ({len(items)}種類)")
        for i, name in enumerate(items, 1):
            print(f"  {i:2}. {name}")
    print(f"\n合計: {sum(len(v) for v in ITEM_MASTER.values())} アイテム")
