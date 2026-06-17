import re
import requests
import zhconv

BASE_URL = "https://prts.wiki"

RARITY_STARS = {
    "1": "★",
    "2": "★★",
    "3": "★★★",
    "4": "★★★★",
    "5": "★★★★★",
    "6": "★★★★★★",
}

HEADERS = {"User-Agent": "PRTSBot/1.0 (Discord Bot for Arknights Wiki)"}
RANGE_DATA_URL = (
    "https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData"
    "/master/zh_CN/gamedata/excel/range_table.json"
)

_operator_cache: list[str] = []
_range_cache: dict = {}


def load_operator_names() -> list[str]:
    global _operator_cache
    if _operator_cache:
        return _operator_cache

    names: list[str] = []
    params: dict = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": "Category:干员",
        "cmlimit": 500,
        "cmnamespace": 0,
        "format": "json",
    }
    while True:
        try:
            r = requests.get(f"{BASE_URL}/api.php", params=params, headers=HEADERS, timeout=15)
            data = r.json()
            names += [x["title"] for x in data["query"]["categorymembers"]]
            if "continue" not in data:
                break
            params["cmcontinue"] = data["continue"]["cmcontinue"]
        except Exception:
            break

    _operator_cache = names
    return _operator_cache


def load_range_data() -> dict:
    global _range_cache
    if _range_cache:
        return _range_cache
    try:
        r = requests.get(RANGE_DATA_URL, headers=HEADERS, timeout=15)
        _range_cache = r.json()
    except Exception:
        _range_cache = {}
    return _range_cache


def render_range(range_id: str) -> str:
    info = load_range_data().get(range_id, {})
    grids = info.get("grids", [])
    if not grids:
        return f"`{range_id}`"

    range_set = {(g["row"], g["col"]) for g in grids}
    all_rows = [g["row"] for g in grids] + [0]
    all_cols = [g["col"] for g in grids] + [0]
    min_row, max_row = min(all_rows), max(all_rows)
    min_col, max_col = min(all_cols), max(all_cols)

    lines = []
    for row in range(max_row, min_row - 1, -1):
        line = []
        for col in range(min_col, max_col + 1):
            if row == 0 and col == 0:
                line.append("🔴")
            elif (row, col) in range_set:
                line.append("🟦")
            else:
                line.append("⬛")
        lines.append("".join(line))
    return "\n".join(lines)


def search_operator_names(query: str) -> list[str]:
    query_s = zhconv.convert(query, "zh-hans")
    return [n for n in load_operator_names() if query_s in n][:25]


def get_operator_data(name: str) -> dict | None:
    name = zhconv.convert(name, "zh-hans")
    params = {
        "action": "parse",
        "page": name,
        "prop": "wikitext",
        "format": "json",
        "redirects": 1,
    }
    try:
        response = requests.get(
            f"{BASE_URL}/api.php", params=params, headers=HEADERS, timeout=10
        )
        data = response.json()
    except Exception:
        return None

    if "error" in data:
        return None

    wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
    if not wikitext:
        return None

    result = _parse_wikitext(wikitext, name)
    result.update(_get_image_urls(name))
    return result


_ELITE_LABELS: dict[int, list[str]] = {
    1: ["精零"],
    2: ["精零", "精二"],
    3: ["精零", "精一", "精二"],
}


def _get_image_urls(name: str) -> dict:
    titles = "|".join(f"文件:立绘_{name}_{i}.png" for i in range(1, 5))
    params = {
        "action": "query",
        "titles": titles,
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
    }
    try:
        r = requests.get(f"{BASE_URL}/api.php", params=params, headers=HEADERS, timeout=10)
        pages = r.json()["query"]["pages"]
    except Exception:
        return {"images": []}

    urls: dict[int, str] = {}
    for page in pages.values():
        if "missing" in page:
            continue
        info = page.get("imageinfo", [])
        if not info:
            continue
        m = re.search(r"(\d+)\.png$", page.get("title", ""))
        if m:
            urls[int(m.group(1))] = info[0]["url"]

    if not urls:
        return {"images": []}

    sorted_urls = [urls[k] for k in sorted(urls.keys())]
    count = len(sorted_urls)
    labels = _ELITE_LABELS.get(count, [f"精{i}" for i in range(count)])
    return {"images": list(zip(labels, sorted_urls))}


def _clean(text: str) -> str:
    text = re.sub(r"\[\[(?:[^\|\]]+\|)?([^\]]+)\]\]", r"\1", text)
    # 保留 color/顯示模板的可見文字，例如 {{color|#hex|文字}} → 文字
    text = re.sub(r"\{\{color\|[^|{}\n]+\|([^{}\n]+)\}\}", r"\1", text)
    text = re.sub(r"\{\{\*\|[^|{}\n]+\|([^{}\n]+)\}\}", r"\1", text)
    # 移除其餘模板
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    # <br> 換行符號轉空格
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"'{2,3}", "", text)
    text = zhconv.convert(text.strip(), "zh-hant")
    return text


def _field(wikitext: str, *names: str) -> str:
    for name in names:
        m = re.search(rf"\|{re.escape(name)}\s*=\s*([^\n]+)", wikitext)
        if m:
            return _clean(m.group(1))
    return ""


def _parse_wikitext(wikitext: str, fallback_name: str) -> dict:
    d: dict[str, str] = {}

    d["name"] = _field(wikitext, "干员名", "幹員名") or fallback_name
    raw_rarity = _field(wikitext, "稀有度")
    d["rarity"] = str(int(raw_rarity) + 1) if raw_rarity.isdigit() else raw_rarity
    d["job_class"] = _field(wikitext, "职业", "職業")
    d["branch"] = _field(wikitext, "分支")
    d["trait"] = _field(wikitext, "特性")
    d["country"] = _field(wikitext, "所属国家", "所屬國家")
    d["organization"] = _field(wikitext, "所属组织", "所屬組織")
    d["tags"] = _field(wikitext, "标签", "標籤")
    d["artist"] = _field(wikitext, "画师", "畫師")
    d["cn_va"] = _field(wikitext, "中文配音")
    d["jp_va"] = _field(wikitext, "日文配音")
    d["en_va"] = _field(wikitext, "英文配音")

    d["block"] = _field(wikitext, "阻挡数", "阻擋數")
    d["cost"] = _field(wikitext, "部署费用", "部署費用")
    d["redeploy"] = _field(wikitext, "再部署")
    d["atk_speed"] = _field(wikitext, "攻击速度", "攻擊速度")

    # 各精英等級滿級屬性
    _STAT_LABEL = {"生命上限": "HP", "攻击": "攻擊", "防御": "防禦", "法术抗性": "法抗"}
    for elite in ("0", "1", "2"):
        parts = []
        for field, label in _STAT_LABEL.items():
            v = _field(wikitext, f"精英{elite}_满级_{field}")
            if v:
                parts.append(f"{label} {v}")
        if parts:
            d[f"stats_e{elite}"] = " ｜ ".join(parts)

    # 信賴加成
    trust = []
    for field, label in {"生命上限": "HP", "攻击": "攻擊", "防御": "防禦"}.items():
        v = _field(wikitext, f"信赖加成_{field}")
        if v and v != "0":
            trust.append(f"{label} +{v}")
    if trust:
        d["trust_bonus"] = " ｜ ".join(trust)

    # 攻擊範圍（原始 ID，供 render_range 使用）
    for elite in ("0", "1", "2"):
        v = _field(wikitext, f"精英{elite}范围")
        if v:
            d[f"range_e{elite}"] = v

    # 潛能提升
    pots = []
    for i in range(2, 7):
        v = _field(wikitext, f"潜能{i}")
        if v:
            pots.append(f"潛能 {i}：{v}")
    if pots:
        d["potentials"] = "\n".join(pots)

    d["file1"] = _field(wikitext, "档案一", "檔案一")
    d["file2"] = _field(wikitext, "档案二", "檔案二")
    d["file3"] = _field(wikitext, "档案三", "檔案三")
    d["file4"] = _field(wikitext, "档案四", "檔案四")

    return {k: v for k, v in d.items() if v}
