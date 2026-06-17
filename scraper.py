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
    # 多輪清理以處理巢狀模板
    for _ in range(4):
        text = re.sub(r"\{\{color\|[^|{}\n]+\|([^{}\n]+)\}\}", r"\1", text)
        text = re.sub(r"\{\{\*\|[^|{}\n]+\|([^{}\n]+)\}\}", r"\1", text)
        text = re.sub(r"\{\{\*\*\|[^|{}\n]+\|([^{}\n]+)\}\}", r"\1", text)
        # {{修正|可見文字|其他參數}} → 可見文字
        text = re.sub(r"\{\{修正\|([^|{}\n]+)(?:\|[^{}]*)?\}\}", r"\1", text)
        # {{变动数值lite|type|color|值}} → 值
        text = re.sub(
            r"\{\{变动数值lite\|[^|{}\n]*\|[^|{}\n]*\|([^|{}\n]+)(?:\|[^{}]*)?\}\}",
            r"\1",
            text,
        )
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"'{2,3}", "", text)
    # 清除殘留的 |欄位名稱= 捕獲污染（來自同行下個欄位）
    if "|" in text:
        text = text[: text.index("|")]
    text = zhconv.convert(text.strip(), "zh-hant")
    return text


def _extract_template_blocks(wikitext: str, template_name: str) -> list[str]:
    """以平衡括號法提取所有 {{template_name...}} 區塊的原始內容。"""
    blocks: list[str] = []
    search = "{{" + template_name
    start = 0
    while True:
        pos = wikitext.find(search, start)
        if pos == -1:
            break
        depth = 0
        i = pos
        while i < len(wikitext) - 1:
            if wikitext[i : i + 2] == "{{":
                depth += 1
                i += 2
            elif wikitext[i : i + 2] == "}}":
                depth -= 1
                i += 2
                if depth == 0:
                    blocks.append(wikitext[pos:i])
                    break
            else:
                i += 1
        start = pos + 2
    return blocks


def _field(wikitext: str, *names: str) -> str:
    for name in names:
        m = re.search(rf"\|{re.escape(name)}\s*=\s*([^\n]+)", wikitext)
        if m:
            return _clean(m.group(1))
    return ""


def _parse_wikitext(wikitext: str, fallback_name: str) -> dict:
    d: dict[str, str] = {}

    d["name"] = _field(wikitext, "干员名", "幹員名") or fallback_name
    d["en_name"] = _field(wikitext, "干员外文名")
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


def get_skill_data(name: str) -> dict | None:
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

    op_name = zhconv.convert(
        _field(wikitext, "干员名", "幹員名") or name, "zh-hant"
    )

    # ── 技能 ──────────────────────────────────────────────────
    def _sp(block: str, prefix: str) -> str:
        init = _field(block, f"{prefix}初始")
        cost = _field(block, f"{prefix}消耗")
        dur  = _field(block, f"{prefix}持续")
        parts: list[str] = []
        if init:
            parts.append(f"初始技力 {init}")
        if cost:
            parts.append(f"消耗技力 {cost}")
        if dur:
            parts.append(f"持續 {dur} 秒")
        return " ｜ ".join(parts)

    skills: list[dict] = []
    for block in _extract_template_blocks(wikitext, "技能"):
        skill_name = _field(block, "技能名")
        if not skill_name:
            continue
        skills.append(
            {
                "name": skill_name,
                "name_en": _field(block, "技能名en"),
                "type1": _field(block, "技能类型1"),
                "type2": _field(block, "技能类型2"),
                "lv7":    _field(block, "技能7描述"),
                "lv7_sp": _sp(block, "技能7"),
                "m1":    _field(block, "技能专精1描述"),
                "m1_sp": _sp(block, "技能专精1"),
                "m2":    _field(block, "技能专精2描述"),
                "m2_sp": _sp(block, "技能专精2"),
                "m3":    _field(block, "技能专精3描述"),
                "m3_sp": _sp(block, "技能专精3"),
            }
        )

    # ── 天賦 ──────────────────────────────────────────────────
    talents: list[dict] = []
    for block in _extract_template_blocks(wikitext, "天赋列表"):
        group = _field(block, "天赋")
        if not group:
            continue
        # 優先取精二效果，沒有則取精一
        t_name = _field(block, "天赋2") or _field(block, "天赋1")
        t_cond = _field(block, "天赋2条件") or _field(block, "天赋1条件")
        t_effect = _field(block, "天赋2效果") or _field(block, "天赋1效果")
        talents.append(
            {"group": group, "name": t_name, "condition": t_cond, "effect": t_effect}
        )

    # ── 模組 ──────────────────────────────────────────────────
    modules: list[dict] = []
    for block in _extract_template_blocks(wikitext, "模组"):
        if "|基础证章=yes" in block:
            continue
        mod_name = _field(block, "名称")
        if not mod_name:
            continue
        modules.append(
            {
                "name": mod_name,
                "type_code": _field(block, "类型"),
                "trait": _field(block, "特性"),
                "talent2": _field(block, "天赋2"),
                "talent3": _field(block, "天赋3"),
            }
        )

    # ── 後勤技能 ────────────────────────────────────────────────
    base_skills: list[dict] = []
    base_blocks = _extract_template_blocks(wikitext, "后勤技能")
    if base_blocks:
        block = base_blocks[0]
        for slot in range(1, 5):
            for tier in range(1, 4):
                prefix = f"后勤技能{slot}-{tier}"
                # 直接用 regex 取簡體名稱（不經 zhconv），供 Cargo 查詢使用
                m = re.search(rf"\|{re.escape(prefix)}\s*=\s*([^\n|}}]+)", block)
                if not m:
                    continue
                cargo_name = m.group(1).strip()
                if not cargo_name:
                    continue
                # 顯示名稱（若有 显示名 欄位則使用，否則用 cargo_name）
                dm = re.search(
                    rf"\|{re.escape(prefix + '显示名')}\s*=\s*([^\n|}}]+)", block
                )
                display = dm.group(1).strip() if dm else cargo_name
                phase = _field(block, f"{prefix}阶段")
                base_skills.append(
                    {
                        "cargo_name": cargo_name,
                        "name": zhconv.convert(display, "zh-hant"),
                        "phase": phase,
                        "room": "",
                        "desc": "",
                    }
                )

    # 批次查詢 Cargo API 取得房間類型與描述（以簡體名查詢）
    if base_skills:
        where = " OR ".join(f"skill.name='{s['cargo_name']}'" for s in base_skills)
        cargo_params = {
            "action": "cargoquery",
            "tables": "building_skill2=skill",
            "where": where,
            "fields": "name,room,description",
            "format": "json",
            "limit": 20,
        }
        try:
            cr = requests.get(
                f"{BASE_URL}/api.php", params=cargo_params, headers=HEADERS, timeout=10
            )
            cargo_map: dict[str, dict] = {
                item["title"]["name"]: item["title"]
                for item in cr.json().get("cargoquery", [])
            }
            for s in base_skills:
                info = cargo_map.get(s["cargo_name"], {})
                s["room"] = zhconv.convert(info.get("room", ""), "zh-hant")
                raw_desc = re.sub(r"<[^>]+>", "", info.get("description", ""))
                s["desc"] = zhconv.convert(raw_desc.strip(), "zh-hant")
        except Exception:
            pass

    return {"name": op_name, "skills": skills[:3], "talents": talents, "modules": modules, "base_skills": base_skills}
