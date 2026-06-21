import random
import re
import requests
import zhconv

BASE_URL = "https://prts.wiki"
WIKIG_BASE = "https://arknights.wiki.gg"
WIKIG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

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
_file_url_cache: dict[str, str] = {}
_image_urls_cache: dict[str, dict] = {}
_skin_url_cache: dict[str, list[str]] = {}
_wikig_op_cache: list[str] = []
_wikig_cn_cache: dict[str, str] = {}        # wiki.gg 英文名 → 繁體中文名
_wikig_voice_url_cache: dict[str, list[str]] = {}  # wiki.gg 英文名 → JP 語音 URL 列表


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


def get_all_operator_names() -> list[str]:
    """回傳已快取的幹員名稱列表（簡體中文）。"""
    return _operator_cache


def _get_skin_urls(hans_name: str) -> list[str]:
    """批次查詢幹員所有時裝立繪 URL（skin1~skin15），結果快取。"""
    if hans_name in _skin_url_cache:
        return _skin_url_cache[hans_name]
    titles = "|".join(f"文件:立绘 {hans_name} skin{i}.png" for i in range(1, 16))
    try:
        r = requests.get(
            f"{BASE_URL}/api.php",
            params={"action": "query", "titles": titles,
                    "prop": "imageinfo", "iiprop": "url", "format": "json"},
            headers=HEADERS, timeout=15,
        )
        pages = r.json().get("query", {}).get("pages", {}).values()
        urls = [
            info[0]["url"]
            for page in pages
            if "missing" not in page
            for info in [page.get("imageinfo", [])]
            if info and info[0].get("url")
        ]
    except Exception:
        urls = []
    _skin_url_cache[hans_name] = urls
    return urls


def get_wife_image(hans_name: str) -> tuple[str, str]:
    """回傳 (繁體名稱, 隨機立繪URL)：精二（或精零）＋所有時裝隨機一項。"""
    trad = zhconv.convert(hans_name, "zh-hant")
    elite_url = _get_file_url(f"立绘_{hans_name}_2.png") or _get_file_url(f"立绘_{hans_name}_1.png")
    portraits = ([elite_url] if elite_url else []) + _get_skin_urls(hans_name)
    return trad, (random.choice(portraits) if portraits else "")


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
    q = zhconv.convert(query, "zh-hans").lower()
    return [n for n in load_operator_names() if q in n.lower()][:25]


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
    if name in _image_urls_cache:
        return _image_urls_cache[name]
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
        _image_urls_cache[name] = {"images": []}
        return _image_urls_cache[name]

    sorted_urls = [urls[k] for k in sorted(urls.keys())]
    count = len(sorted_urls)
    labels = _ELITE_LABELS.get(count, [f"精{i}" for i in range(count)])
    result = {"images": list(zip(labels, sorted_urls))}
    _image_urls_cache[name] = result
    return result


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


def _parse_materials(text: str) -> list[tuple[str, str]]:
    """解析 {{材料消耗|名稱|數量}} 模板，回傳 (繁體名稱, 數量) 列表。"""
    items = re.findall(r"\{\{材料消耗\|([^|{}]+)\|([^{}]+)\}\}", text)
    return [(zhconv.convert(n.strip(), "zh-hant"), zhconv.convert(q.strip(), "zh-hant")) for n, q in items]


def get_material_data(name: str) -> dict | None:
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

    # ── 技能名稱（依序對應一/二/三）────────────────────────────────
    skill_names: list[str] = []
    for block in _extract_template_blocks(wikitext, "技能"):
        sn = _field(block, "技能名")
        if sn:
            skill_names.append(sn)

    # ── 技能專精材料 ──────────────────────────────────────────────
    masteries: list[dict] = []
    upgrade_blocks = _extract_template_blocks(wikitext, "技能升级材料")
    if upgrade_blocks:
        ub = upgrade_blocks[0]
        for i, prefix in enumerate(("一", "二", "三")):
            m1 = re.search(rf"\|{prefix}8\s*=\s*([^\n]+)", ub)
            if not m1:
                continue
            m2 = re.search(rf"\|{prefix}9\s*=\s*([^\n]+)", ub)
            m3 = re.search(rf"\|{prefix}10\s*=\s*([^\n]+)", ub)
            masteries.append(
                {
                    "name": skill_names[i] if i < len(skill_names) else f"技能{i+1}",
                    "m1": _parse_materials(m1.group(1)),
                    "m2": _parse_materials(m2.group(1) if m2 else ""),
                    "m3": _parse_materials(m3.group(1) if m3 else ""),
                }
            )

    # ── 模組解鎖材料 ──────────────────────────────────────────────
    mod_materials: list[dict] = []
    for block in _extract_template_blocks(wikitext, "模组"):
        if "|基础证章=yes" in block:
            continue
        mn = re.search(r"\|名称\s*=\s*([^\n|{}]+)", block)
        if not mn:
            continue
        mt = re.search(r"\|类型\s*=\s*([^\n|{}]+)", block)
        ul = re.search(r"\|解锁等级\s*=\s*([^\n|{}]+)", block)
        ut = re.search(r"\|解锁信赖\s*=\s*([^\n|{}]+)", block)
        c1 = re.search(r"\|材料消耗\s*=\s*([^\n]+)", block)
        c2 = re.search(r"\|材料消耗2\s*=\s*([^\n]+)", block)
        c3 = re.search(r"\|材料消耗3\s*=\s*([^\n]+)", block)
        mod_materials.append(
            {
                "name": zhconv.convert(mn.group(1).strip(), "zh-hant"),
                "type_code": zhconv.convert(mt.group(1).strip(), "zh-hant") if mt else "",
                "unlock_level": ul.group(1).strip() if ul else "",
                "unlock_trust": ut.group(1).strip() if ut else "",
                "cost1": _parse_materials(c1.group(1) if c1 else ""),
                "cost2": _parse_materials(c2.group(1) if c2 else ""),
                "cost3": _parse_materials(c3.group(1) if c3 else ""),
            }
        )

    return {"name": op_name, "masteries": masteries, "mod_materials": mod_materials}


def get_lore_data(name: str) -> dict | None:
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

    sections: list[dict] = []
    for n in range(1, 15):
        title_m = re.search(rf"\|档案{n}\s*=\s*([^\n|{{}}]+)", wikitext)
        if not title_m:
            break
        title = zhconv.convert(title_m.group(1).strip(), "zh-hant")

        cond_m = re.search(rf"\|档案{n}条件\s*=\s*([^\n|{{}}]+)", wikitext)
        condition = zhconv.convert(cond_m.group(1).strip(), "zh-hant") if cond_m else ""

        # 多行內容：遇到下一個欄位、模板結尾 }} 或 ==章節== 即停止
        content_m = re.search(
            r"\|档案" + str(n) + r"文本\s*=\s*(.*?)(?=\n\||\n}}|\n==|\Z)", wikitext, re.DOTALL
        )
        content = ""
        if content_m:
            raw = content_m.group(1).strip()
            raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
            raw = re.sub(r"<[^>]+>", "", raw)
            raw = re.sub(r"\[\[(?:[^\|\]]+\|)?([^\]]+)\]\]", r"\1", raw)
            raw = re.sub(r"\{\{[^{}]*\}\}", "", raw)
            content = zhconv.convert(raw.strip(), "zh-hant")

        sections.append({"title": title, "condition": condition, "content": content})

    return {"name": op_name, "sections": sections}


def _get_file_url(file_name: str) -> str:
    if file_name in _file_url_cache:
        return _file_url_cache[file_name]
    try:
        r = requests.get(
            f"{BASE_URL}/api.php",
            params={
                "action": "query",
                "titles": f"File:{file_name}",
                "prop": "imageinfo",
                "iiprop": "url",
                "format": "json",
            },
            headers=HEADERS,
            timeout=10,
        )
        for page in r.json().get("query", {}).get("pages", {}).values():
            info = page.get("imageinfo", [])
            if info:
                url = info[0].get("url", "")
                _file_url_cache[file_name] = url
                return url
    except Exception:
        pass
    _file_url_cache[file_name] = ""
    return ""
    return ""


def get_skin_data(name: str) -> dict | None:
    hans_name = zhconv.convert(name, "zh-hans")
    params = {
        "action": "parse",
        "page": hans_name,
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
        _field(wikitext, "干员名", "幹員名") or hans_name, "zh-hant"
    )

    # ── 從幹員主頁取得時裝清單 ─────────────────────────────────────
    outfits: list[tuple[int, str, str]] = []  # (index, name_hans, series_base_hans)
    for n in range(1, 20):
        name_m = re.search(rf"\|时装{n}名称\s*=\s*([^\n|{{}}]+)", wikitext)
        if not name_m:
            break
        skin_name = name_m.group(1).strip()
        series_m = re.search(rf"\|时装{n}系列\s*=\s*([^\n|{{}}]+)", wikitext)
        series_full = series_m.group(1).strip() if series_m else ""
        series_base = series_full.split("/")[0].strip()
        outfits.append((n, skin_name, series_base))

    if not outfits:
        return {"name": op_name, "skins": []}

    # ── 按系列批次取得 画师/价格 ───────────────────────────────────
    series_cache: dict[str, dict[str, dict]] = {}
    for _, _, series_base in outfits:
        if not series_base or series_base in series_cache:
            continue
        try:
            r = requests.get(
                f"{BASE_URL}/api.php",
                params={
                    "action": "parse",
                    "page": f"时装回廊/{series_base}",
                    "prop": "wikitext",
                    "format": "json",
                },
                headers=HEADERS,
                timeout=10,
            )
            series_wt = r.json().get("parse", {}).get("wikitext", {}).get("*", "")
        except Exception:
            series_wt = ""

        skin_index: dict[str, dict] = {}
        for block in _extract_template_blocks(series_wt, "干员时装"):
            bn_m = re.search(r"\|时装名\s*=\s*([^\n|{}]+)", block)
            if not bn_m:
                continue
            bname = bn_m.group(1).strip()
            artist_m = re.search(r"\|画师\s*=\s*([^\n|{}]+)", block)
            route_m  = re.search(r"\|获得途径\s*=\s*([^\n]+)", block)
            price_m  = re.search(r"\|价格\s*=\s*([^\n|{}]+)", block)

            artist = zhconv.convert(artist_m.group(1).strip(), "zh-hant") if artist_m else ""
            route_raw = route_m.group(1).strip() if route_m else ""
            # 清除 wikilink
            route_clean = re.sub(r"\[\[[^\]]*\|([^\]]+)\]\]", r"\1", route_raw)
            route_clean = re.sub(r"\[\[([^\]]+)\]\]", r"\1", route_clean).strip()

            if "采购中心" in route_clean and price_m:
                price = f"{price_m.group(1).strip()} 源石結晶"
            else:
                price = "活動、禮包獲得"

            skin_index[bname] = {"artist": artist, "price": price}

        series_cache[series_base] = skin_index

    # ── 組合最終結果並取得圖片 URL ──────────────────────────────────
    skins: list[dict] = []
    for skin_n, skin_name_hans, series_base in outfits:
        info = series_cache.get(series_base, {}).get(skin_name_hans, {})
        image_url = _get_file_url(f"立绘 {hans_name} skin{skin_n}.png")
        skins.append(
            {
                "name": zhconv.convert(skin_name_hans, "zh-hant"),
                "series": zhconv.convert(series_base, "zh-hant"),
                "artist": info.get("artist", ""),
                "price": info.get("price", ""),
                "image_url": image_url,
            }
        )

    return {"name": op_name, "skins": skins}


# ── 角色真名快取 ───────────────────────────────────────────────────
_real_name_cache: dict[str, dict] = {}  # 簡體代號 → {codename, real_name, source, avatar_url}


def _clean_real_name(text: str) -> str:
    """清理真名欄位的 wikitext 標記，保留可讀文字。"""
    # 移除 ref 標籤
    text = re.sub(r"<ref[^/]*/?>.*?</ref>|<ref[^>]*/>", "", text, flags=re.DOTALL)
    # {{popup|交互=1|可見文字|内容=...}} → 可見文字
    text = re.sub(
        r"\{\{popup\|[^|{}]*\|([^|{}]*(?:\{\{[^{}]*\}\}[^|{}]*)*)\|内容=[^{}]*\}\}",
        lambda m: re.sub(r"<[^>]+>", "", m.group(1)),
        text,
    )
    # {{Color|...|文字}} → 文字
    text = re.sub(r"\{\{[Cc]olor\|[^|{}]+\|([^{}]+)\}\}", r"\1", text)
    # {{mdi|arrow-right}} → →
    text = re.sub(r"\{\{mdi\|arrow-right\}\}", "→", text)
    # <span ...>文字</span> → 文字
    text = re.sub(r"<span[^>]*>(.*?)</span>", r"\1", text, flags=re.DOTALL)
    # <del>文字</del> → ~~文字~~（刪除線）
    text = re.sub(r"<del>(.*?)</del>", r"~~\1~~", text)
    # [[link|display]] → display
    text = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", text)
    # [[link]] → link
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    # <br> → 、
    text = re.sub(r"<br\s*/?>", "、", text, flags=re.IGNORECASE)
    # 殘餘 HTML 標籤
    text = re.sub(r"<[^>]+>", "", text)
    # 斜體 ''...'' → ...
    text = re.sub(r"''(.*?)''", r"\1", text)
    # 剩餘 {{ }} 模板
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    return text.strip()


def load_real_names() -> dict[str, dict]:
    """載入並快取角色真名頁面的所有資料。"""
    global _real_name_cache
    if _real_name_cache:
        return _real_name_cache

    try:
        r = requests.get(
            f"{BASE_URL}/api.php",
            params={
                "action": "parse",
                "page": "角色真名",
                "prop": "wikitext",
                "format": "json",
            },
            headers=HEADERS,
            timeout=15,
        )
        wt = r.json().get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        return {}

    # 移除 HTML 注釋（<!--...-->）中的內容
    wt_clean = re.sub(r"<!--.*?-->", "", wt, flags=re.DOTALL)

    # 第一步：解析所有列，收集代號、真名、出處
    # row tuple: (codename_hans, real_name, source, is_operator)
    rows: list[tuple[str, str, str, bool]] = []
    _avatar_pat = re.compile(r"\{\{(干员头像|敌人头像)\|([^|}]+)")
    for line in wt_clean.split("\n"):
        line = line.strip()
        if not (line.startswith("|{{干员头像|") or line.startswith("|{{敌人头像|")):
            continue
        cells = line.split("||")
        if len(cells) < 3:
            continue
        m = _avatar_pat.search(cells[0])
        if not m:
            continue
        is_operator = m.group(1) == "干员头像"
        codename_hans = m.group(2).strip()
        real_name = _clean_real_name(cells[2].strip())
        source = _clean_real_name(cells[3].strip() if len(cells) > 3 else "")
        rows.append((codename_hans, real_name, source, is_operator))

    # 第二步：批次查詢頭像 URL（每批最多 50 筆，幹員/非幹員皆試 头像_{name}.png）
    avatar_urls: dict[str, str] = {}
    batch_size = 50
    all_names = [r[0] for r in rows]
    for i in range(0, len(all_names), batch_size):
        batch_names = all_names[i : i + batch_size]
        titles = "|".join(f"File:头像_{name}.png" for name in batch_names)
        try:
            resp = requests.get(
                f"{BASE_URL}/api.php",
                params={
                    "action": "query",
                    "titles": titles,
                    "prop": "imageinfo",
                    "iiprop": "url",
                    "format": "json",
                },
                headers=HEADERS,
                timeout=15,
            )
            for page in resp.json().get("query", {}).get("pages", {}).values():
                if "missing" in page:
                    continue
                info = page.get("imageinfo", [])
                if not info:
                    continue
                title = page.get("title", "")
                name_m = re.search(r"头像_(.+)\.png$", title)
                if name_m:
                    avatar_urls[name_m.group(1)] = info[0]["url"]
        except Exception:
            pass

    # 第三步：組合結果
    result: dict[str, dict] = {}
    for codename_hans, real_name, source, is_operator in rows:
        result[codename_hans] = {
            "codename": zhconv.convert(codename_hans, "zh-hant").replace("嶽", "岳"),
            "real_name": zhconv.convert(real_name, "zh-hant"),
            "source": zhconv.convert(source, "zh-hant"),
            "avatar_url": avatar_urls.get(codename_hans, ""),
            "is_operator": is_operator,
        }

    _real_name_cache = result
    return result


def get_real_name(query: str) -> dict | None:
    """依代號（支援繁簡）查詢角色真名資料。"""
    query_hans = zhconv.convert(query, "zh-hans")
    data = load_real_names()
    return data.get(query_hans)


def search_real_names(query: str) -> list[str]:
    """自動完成：回傳符合查詢的代號列表（繁體，最多25筆）。"""
    q = zhconv.convert(query, "zh-hans").lower()
    data = load_real_names()
    matched = [
        data[k]["codename"]
        for k in data
        if q in k.lower()
    ]
    return matched[:25]


def _table_rows(text: str) -> list[str]:
    """依照頂層 |- 分割 wiki 表格，跳過嵌套 {| |} 內的 |-。
    depth 從 -1 開始，讓外層 {| 進入 depth=0（即「在外層表格內」）。
    """
    rows, current, depth = [], [], -1
    for line in text.split("\n"):
        depth += line.count("{|") - line.count("|}")
        if depth == 0 and line.strip().startswith("|-"):
            if current:
                rows.append("\n".join(current))
            current = []
        else:
            current.append(line)
    if current:
        rows.append("\n".join(current))
    return rows


def _row_cells(row: str) -> list[str]:
    """從表格行取得各欄位，跳過嵌套表格和模板內的 | 分隔。"""
    cells, current, tbl_depth, tmpl_depth, in_cell = [], [], 0, 0, False
    for line in row.split("\n"):
        # 先判斷是否為新 cell（使用「本行前」的深度）
        if tbl_depth == 0 and tmpl_depth == 0 and line.startswith("|") and not line.startswith("|-"):
            if in_cell:
                cells.append("\n".join(current))
            current = [line[1:]]
            in_cell = True
        else:
            current.append(line)
        # 更新深度（本行結束後）
        tbl_depth = max(0, tbl_depth + line.count("{|") - line.count("|}"))
        tmpl_depth = max(0, tmpl_depth + line.count("{{") - line.count("}}"))
    if current and in_cell:
        cells.append("\n".join(current))
    return cells


# ── 集成戰略資料 ─────────────────────────────────────────────────────

IS_CONFIGS: dict[str, dict] = {
    "刻俄柏的灰蕈迷境": {"num": 1, "relic_page": "刻俄柏的灰蕈迷境/收藏品图鉴", "trad": "刻俄柏的灰蕈迷境"},
    "傀影与猩红孤钻": {"num": 2, "relic_page": "傀影与猩红孤钻/长生者宝盒", "trad": "傀影與猩紅孤鑽"},
    "水月与深蓝之树": {"num": 3, "relic_page": "水月与深蓝之树/生物制品陈设", "trad": "水月與深藍之樹"},
    "探索者的银凇止境": {"num": 4, "relic_page": "探索者的银凇止境/仪式用品索引", "trad": "探索者的銀凇止境"},
    "萨卡兹的无终奇语": {"num": 5, "relic_page": "萨卡兹的无终奇语/想象实体图鉴", "trad": "薩卡茲的無終奇語"},
    "岁的界园志异": {"num": 6, "relic_page": "岁的界园志异/珍玩集册", "trad": "歲的界園志異"},
}

_is_main_wt_cache: dict[str, str] = {}
_is_relic_cache: dict[str, list[dict]] = {}


def _get_is_main_wt(is_name_hans: str) -> str:
    if is_name_hans in _is_main_wt_cache:
        return _is_main_wt_cache[is_name_hans]
    try:
        r = requests.get(
            f"{BASE_URL}/api.php",
            params={"action": "parse", "page": is_name_hans, "prop": "wikitext", "format": "json"},
            headers=HEADERS, timeout=20,
        )
        wt = r.json().get("parse", {}).get("wikitext", {}).get("*", "")
        _is_main_wt_cache[is_name_hans] = wt
        return wt
    except Exception:
        return ""


def _clean_is_text(text: str) -> str:
    """清理 IS 頁面的 wikitext，保留可讀文字（支援換行）。"""
    # 移除 cell 前綴 `| style="..." |`（只匹配不含 { } 的前綴，避免誤切模板引數）
    text = re.sub(r"^(?:[^|{}\n]*\|)(?!\|)", "", text.strip())
    # 多次迭代清理巢狀模板
    for _ in range(4):
        # {{popup|交互=1|可見文字|内容=...}} → 可見文字
        text = re.sub(
            r"\{\{popup\|交互=1\|([^|{}]*)\|[^{}]*\}\}",
            lambda m: re.sub(r"<[^>]+>", "", m.group(1)),
            text,
        )
        # {{popup|可見文字|内容=...}} → 可見文字
        text = re.sub(
            r"\{\{popup\|([^|{}]*)\|(?:内容|颜色)[^{}]*\}\}",
            lambda m: re.sub(r"<[^>]+>", "", m.group(1)),
            text,
        )
        # {{修正|可見|...}} → 可見
        text = re.sub(r"\{\{修正\|([^|{}]*)\|[^{}]*\}\}", r"\1", text)
        # {{color|...|text}} / {{Color|...|text}} → text
        text = re.sub(r"\{\{[Cc]olor\|[^|{}]+\|([^{}]+)\}\}", r"\1", text)
        # {{Font|original|css=...}} → original
        text = re.sub(r"\{\{Font\|([^|{}]+)\|[^{}]*\}\}", r"\1", text)
        # 移除無參數或全簡單模板
        text = re.sub(r"\{\{[^|{}]{1,40}\}\}", "", text)
    # [[文件:...|...]] 和 [[File:...|...]] → 空
    text = re.sub(r"\[\[(?:文件|File|档案):[^\]]*\]\]", "", text)
    # [[link|display]] → display；[[link]] → link
    text = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    # 粗體/斜體
    text = re.sub(r"'{2,3}([^'\n]+)'{2,3}", r"\1", text)
    # 移除剩餘巢狀模板（平衡括號法）
    out, depth, i = [], 0, 0
    while i < len(text):
        if text[i : i + 2] == "{{":
            depth += 1; i += 2
        elif text[i : i + 2] == "}}":
            if depth > 0: depth -= 1
            i += 2
        elif depth == 0:
            out.append(text[i]); i += 1
        else:
            i += 1
    text = "".join(out)
    # <br> → \n；只移除英文字母開頭的 HTML 標籤（保留 <遊戲名詞> 這類文字）
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/?\s*[a-zA-Z][^>]*>", "", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_table_with_header(section: str, header_key: str) -> str:
    """在 section 中找包含 header_key 的 wikitable，回傳完整的 {|...|} 字串。"""
    idx = section.find(header_key)
    if idx < 0:
        return ""
    start = section.rfind("{|", 0, idx)
    if start < 0:
        return ""
    depth, i = 0, start
    while i < len(section):
        if section[i : i + 2] == "{|":
            depth += 1; i += 2
        elif section[i : i + 2] == "|}":
            depth -= 1
            if depth == 0:
                return section[start : i + 2]
            i += 2
        else:
            i += 1
    return section[start:]


def get_is_difficulty(is_name_hans: str) -> list[dict]:
    """回傳各難度等級資料：{name, level, conditions, score}。"""
    cfg = IS_CONFIGS.get(is_name_hans, {})
    wt = _get_is_main_wt(is_name_hans)
    if not wt:
        return []

    if cfg.get("num") == 1:
        # IS#1：解析 bullet points
        sec_m = re.search(r"(?:==+ *探索难度.*?==+)(.*?)(?:==)", wt, re.DOTALL)
        if not sec_m:
            return []
        content = sec_m.group(1)
        results = []
        for m in re.finditer(r"\*\s*\{\{color\|[^|{}]+\|'''([^']+)'''\}\}\s*([^\n]*)", content):
            name = m.group(1).strip()
            desc = _clean_is_text(m.group(2).strip())
            results.append({"name": name, "level": "", "conditions": desc, "score": ""})
        return results

    # IS#2-6：找 常規行動 section
    sec_m = re.search(r"=== 常规行动 ===(.*?)(?====|\Z)", wt, re.DOTALL)
    if not sec_m:
        return []
    content = sec_m.group(1)

    # IS#2 有 tabber，取第一 tab（現行難度）
    if "<tabber>" in content:
        content = re.sub(r"</?tabber>", "", content)
        content = content.split("|-|")[0]
    content = re.sub(r"<nowiki/>", "", content)

    table = _extract_table_with_header(content, "! 难度")
    if not table:
        return []

    results: list[dict] = []
    for row in _table_rows(table):
        cells = _row_cells(row)
        # 難度行至少需要 4 欄：icon / 名稱 / 等級 / 追加條件
        if len(cells) < 4:
            continue

        # cell[1] = 難度名稱（取清理後的第一行）
        name = _clean_is_text(cells[1]).split("\n")[0].strip()
        if not name or "——" in name:
            continue

        # cell[2] = 等級
        level = _clean_is_text(cells[2]).strip()
        if not re.match(r"^(\d+|N/A)$", level):
            level = ""

        # cell[3] = 追加條件（只取 <br> 前的第一句）
        first_part = re.split(r"<br\s*/?>", cells[3], maxsplit=1, flags=re.IGNORECASE)[0]
        conditions = _clean_is_text(first_part).strip()[:200]

        # cell[4+] = 找得分效率（第一個純 % 值）
        score = ""
        for cell in cells[4:]:
            c = _clean_is_text(cell).strip()
            if re.match(r"^[±+\-−]?\d+%$", c):
                score = c
                break

        results.append({"name": name, "level": level, "conditions": conditions, "score": score})

    return results


def get_is_squads(is_name_hans: str) -> list[dict]:
    """回傳分隊資料：{name, effect, unlock}。"""
    cfg = IS_CONFIGS.get(is_name_hans, {})
    wt = _get_is_main_wt(is_name_hans)
    if not wt:
        return []

    if cfg.get("num") == 1:
        sec_m = re.search(r"=== 战术分队 ===(.*?)(?====|\Z)", wt, re.DOTALL)
    else:
        sec_m = re.search(r"=== 常规行动 ===(.*?)(?====|\Z)", wt, re.DOTALL)
    if not sec_m:
        return []
    content = sec_m.group(1)

    if cfg.get("num") != 1:
        idx = content.find("选择分队")
        if idx < 0:
            return []
        content = content[idx:]

    table = _extract_table_with_header(content, "! 分队")
    if not table:
        return []

    results: list[dict] = []
    for row in _table_rows(table):
        cells = _row_cells(row)
        if len(cells) < 2:
            continue
        # Cell 0：圖片 + <br> + 名稱
        c0 = _clean_is_text(cells[0])
        parts0 = [p.strip() for p in c0.split("\n") if p.strip()]
        name = parts0[-1] if parts0 else ""
        if not name or len(name) < 2:
            continue
        # Cell 1：效果 || 解鎖條件（同一行）
        c1_raw = cells[1]
        inline = c1_raw.split("||")
        effect = _clean_is_text(inline[0])
        unlock = _clean_is_text(inline[1]) if len(inline) > 1 else ""
        # 若 cells[2] 存在則優先取 unlock
        if len(cells) >= 3 and not unlock:
            unlock = _clean_is_text(cells[2])

        trad_name = zhconv.convert(name, "zh-hant")
        if trad_name and trad_name not in {"分隊", "效果", "解鎖條件"}:
            results.append({
                "name": trad_name,
                "effect": zhconv.convert(effect, "zh-hant")[:400],
                "unlock": zhconv.convert(unlock, "zh-hant")[:100],
            })

    return results


def _load_is_relics(is_name_hans: str) -> list[dict]:
    """載入並快取指定 IS 的收藏品資料。"""
    if is_name_hans in _is_relic_cache:
        return _is_relic_cache[is_name_hans]
    cfg = IS_CONFIGS.get(is_name_hans, {})
    relic_page = cfg.get("relic_page", "")
    if not relic_page:
        return []
    try:
        r = requests.get(
            f"{BASE_URL}/api.php",
            params={"action": "parse", "page": relic_page, "prop": "wikitext", "format": "json"},
            headers=HEADERS, timeout=20,
        )
        wt = r.json().get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        return []

    results: list[dict] = []
    # 只匹配 {{收藏品\n（排除 {{收藏品/...}}）
    for block in _extract_template_blocks(wt, "收藏品\n"):
        fields: dict[str, str] = {}
        for m in re.finditer(r"\|(\w+)\s*=\s*(.*?)(?=\n\||\n\}\}|\Z)", block, re.DOTALL):
            fields[m.group(1)] = m.group(2).strip()
        name = fields.get("名称", "")
        if not name:
            continue
        results.append({
            "id": fields.get("ID", ""),
            "name": name,
            "name_trad": zhconv.convert(name, "zh-hant"),
            "rarity": int(fields.get("稀有度", "0") or "0"),
            "price": fields.get("售价", ""),
            "effect": zhconv.convert(_clean_is_text(fields.get("效果", "")), "zh-hant"),
            "description": zhconv.convert(_clean_is_text(fields.get("描述", "")), "zh-hant"),
        })

    _is_relic_cache[is_name_hans] = results
    return results


def search_is_relic_names(is_name_hans: str, query: str) -> list[str]:
    """自動完成：回傳符合查詢的收藏品名稱（繁體），最多 25 筆。"""
    relics = _load_is_relics(is_name_hans)
    q = zhconv.convert(query, "zh-hans").lower()
    matched = [r["name_trad"] for r in relics if q in r["name"].lower() or q in r["name_trad"].lower()]
    return matched[:25]


def get_is_relic(is_name_hans: str, relic_query: str) -> dict | None:
    """依名稱（繁簡均可）查詢收藏品資料。"""
    relics = _load_is_relics(is_name_hans)
    q = zhconv.convert(relic_query, "zh-hans").lower()
    for r in relics:
        if q == r["name"].lower() or q in r["name"].lower():
            return r
    return None


_story_char_cache: list[dict] = []
_operator_gender_cache: dict[str, str] = {}  # name_hans → 男/女/未知

# 指定劇情角色使用的立繪索引（key 為簡體名稱，value 為 image_urls 的索引）
PORTRAIT_INDEX_OVERRIDES: dict[str, int] = {
    "弑君者": 1,
    "梅菲斯特": 2,
    "浮士德": 2,
}

# 手動性別覆蓋（優先於自動抓取，key 為簡體名稱）
GENDER_OVERRIDES: dict[str, str] = {
    # ── 幹員（原始設定）──
    "Logos": "男", "解真": "男", "太合": "男", "说书人": "男",
    "老骑士": "男", "老工匠": "男", "大嘴莫布": "男", "光头马丁": "男",
    "恰尔内": "男", "马克维茨": "男", "塑料骑士": "男", "锈铜骑士": "男",
    "左手骑士": "男", "腐败骑士": "男", "凋零骑士": "男", "罗伊": "男",
    "逐魇骑士": "男", "莱姆": "男", "坎诺特": "男", "克洛宁": "男",
    "伊比利亚主教": "男", "老何塞": "男", "希尔": "女", "麦克马丁": "男",
    "大祭司": "男", "大长老": "男", "老伊辛": "男", "大帝": "男",
    "伊斯": "男", "昆图斯": "男", "D.D.D.": "男",
    "莫妮克": "女", "莫希": "女", "Aya": "女", "Alty": "女",
    "Dan": "女", "Frost": "女",
    # ── 劇情角色（圖片辨認）──
    # 男
    "卢比奥之女": "女",
    "普瑞赛斯": "女",
    "费奥多尔·弗拉基米罗维奇": "男", "勒内·莱托": "男",
    "维斯利·威灵顿": "男", "卡铎尔": "男",
    "西尔莎·凯利": "女", "“变形者集群”": "女", "卡谢娜": "女",
    "艾尔希": "女", "茉莉": "女", "萨卢斯": "女",
    "珀茜瓦尔": "女", "希勒少尉": "男",
    "菈玛莲": "女", "厄尔苏拉": "女", "芙蕾达·韦斯特": "女",
    "肖恩·高多汀": "男", "娜汀": "女", "希尔达": "女",
    "阿洛伊泽": "女", "雷尔金": "男", "尼克托": "男", "霍里": "男",
    "叶莉莎女大公": "女",
    "斯韦特兰纳·乌里扬诺娃·卜捷里娜": "女",
    "阿纳托利·斯维特拉诺夫·卜捷里宁": "男",
    "叶甫根尼·库兹涅佐夫": "男", "西尔卡": "女",
    "艾丽塔·瓦卢耶娃": "女", "克利姆": "男",
    "“伊凡·图林”": "女", "纳杰日达": "女",
    "普拉多·卢宁": "男", "“纳斯塔霞”": "女", "萨满": "女",
    "疤眼": "男", "尤莉叶": "女", "“好运”": "男",
    "艾莉诺": "女", "黛安·韦伯": "女",
    "帕尤卡卡": "男", "弥尔顿": "男",
    "法杰伊": "男", "巴普洛维奇": "男", "格罗莫夫": "男",
    "瓦西里·戈尔奇科夫": "男", "仲裁人": "男",
    "安托沙": "男", "马特维": "男",
    "尤拉": "男", "尼卡": "女", "“小个子”": "男",
    "塞茜莉亚·拉珀尔塔": "女", "奥伦·亚吉奥拉斯": "男",
    "罗塞菈": "女", "安多恩·雅迦坦哲罗思": "男",
    "杰拉尔德": "男", "克莱芒·杜波瓦": "男", "莱蒙德": "男",
    "福尔图娜": "女", "奥卢斯": "男",
    "德尔菲娜": "女", "艾伦戴尔": "男", "艾丝塔拉": "女",
    "梵里妮": "女", "潘格尼尼": "男", "伊蒂达": "女",
    "阿摩斯": "男", "奥罗拉": "女", "老修士": "男",
    "塔季扬娜·叶甫盖尼耶夫娜·拉里娜": "女", "卡罗琳": "女",
    "阿德颂·布朗陶": "男", "菲利帕": "女", "瓦拉赫": "男",
    "丹布朗·莱奥帕尔迪": "男",
    "伊雷妮·拉瓦萨": "女", "翁贝托·德蒙塔诺": "男",
    "安东尼奥·威尼斯": "男", "法布里齐奥·威尼斯": "男",
    "索默尔": "男", "露彼娜": "女",
    "伊奥莱塔·罗素": "女", "托兰·卡什": "男", "切斯柏": "男",
    "郑清钺": "男", "慎楼": "男",
    "杜遥夜": "女", "宁辞秋": "女", "尚冢": "男",
    "槐天裴": "男", "左宣辽": "男", "孟铁衣": "男",
    "睚": "男", "山海众头目": "男", "萨尔贡游客": "男",
    "颉": "女", "方小石": "男", "村长": "男", "猎户": "男",
    "万勤城（万侍郎）": "男", "神农": "女", "绩": "男",
    "老天师": "女", "沉默的樵夫": "男", "太尉": "男",
    "虞澄": "男", "谌彻": "女", "宁述": "男", "顾筌": "男",
    "老姜": "男", "“小教头”": "男", "景教授": "女", "莫不服": "男",
    "莫佚": "女", "渡魂剑": "女", "蒲先生": "男", "易": "男",
    "兰可": "男", "白锦": "女", "椿": "女", "均": "女",
    "陈昭芊": "女", "布莱克": "男",
    "贾斯汀·菲茨罗伊（小贾斯汀）": "男",
    "洛肯·威廉姆斯": "男", "康拉德·杰克逊": "男",
    "雅拉·布克·威尔森": "女",
    "斯凯·杰洛": "男", "古斯塔夫·博内": "男",
    "梅希亚·塞勒涅": "女", "拂哀菈": "女", "雅斯彭": "男",
    "大审判官达里奥": "男", "佩特拉奶奶": "女",
    "最后的骑士": "男",
    # 名字直接判斷
    "克莱门莎": "女", "布兰都斯": "男", "阿维图斯": "男",
    "卡西娅": "女", "图利娅": "女", "玛利图斯": "男",
    "赫拉提娅": "女", "哈维尔": "男", "胡安娜": "女",
    "安纳斯塔西奥": "男", "鲁斯": "男",
    "莉泽洛特·伊维格娜德": "女", "希尔德加德·赫琳玛特": "女",
    "沃里克伯爵": "男", "维恩": "男", "塞尔蒙": "男",
    "开斯特公爵": "女", "放逐王": "男",
    "涅梅丝": "女", "艾玛": "女", "坎黛拉·桑切斯": "女",
    "潘乔·萨拉斯": "男", "卡恩": "男",
    "路特": "男", "丽芙": "女", "佩利佩·布朗": "男",
    "汤姆": "男", "祖拜尔": "男",
    "铁斋": "男", "三船光平": "男", "澪": "女",
    "反町哲也": "男", "锦织更纱": "女", "惟任刑警": "男",
    "里昂·特雷门": "男", "“桥夹”克里夫": "男",
    "伍德洛·比安奇": "男", "迈尔斯": "男",
    "西尔维娅": "女", "本尼": "男", "格蕾塔·斯通": "女",
    "斯蒂芬·奎": "男", "米兰妮·卢瑟福德": "女",
    "迈克尔": "男", "玛丽昂": "女", "阿布纳": "男",
    "谢莉": "女", "莫伊拉": "女", "道尔顿": "男",
    "劳拉": "女", "卡珊卓拉": "女",
    "里底娅·阿苏普欧洛": "女",
    "西塞罗": "男", "阿雅妮": "女",
    "泷居应": "男", "利藤裕": "男",
    "柏生义冈": "男", "柏生明": "男", "泷居未来": "女",
    "雷内尔·科瓦尔斯基": "男", "米沃什": "男",
    "马特奥": "男", "迪亚兹·冈萨雷斯": "男", "沃尔夫": "男",
    "“睦的母亲”": "女", "“父亲”": "男", "“母亲”": "女",
    "未知男性卡特斯": "男", "杰里": "男",
    "列维·克里奇科": "男", "阿根": "男",
    "安德涅特·马里亚姆": "女",
    "“阿米娅”，炉芯终曲": "女",
    # 圖片辨認（第二批）
    "蒂奇": "男", "西尔弗": "男",
    "赫尔昏佐伦，“巫王”": "男", "“校官”": "男",
    "伯德": "女", "凯勒": "女", "哈莉": "女",
    "阿雅吉": "女", "来自黄金之城的使者": "女",
    "宫司": "男", "“酒神”": "男", "列尔": "男",
    "霍汀": "女", "贝赫努": "男", "赫卡德墨": "男",
    "吕刻伊昂": "女", "佩里安德洛斯": "男",
    "西妮斯卡": "女", "梅里塔": "女", "乞丐": "男",
    "橡杯": "女", "莫菲丝": "女", "卡莱莎": "女",
    '博卓卡斯替，圣卫铳骑': "男", '奎隆，摩诃萨埵权化': "男",
    "“木裂”埃克提尔尼尔": "男", "“剧团喉舌”": "男",
    "无名剧作家": "男", "后": "男", "佐恩": "男",
    "小白": "女", "柳千秋": "女",
    "克伦妮": "女",
    # 名字可判斷（無圖）
    "阿利斯泰尔": "男", "查尔斯·林奇": "男", "赫曼": "男",
    "恺撒": "男", "卢比奥": "男",
    "西西里夫人": "女", "诺埃米": "女", "埃芒加德": "女",
    "安费丽丝·温德米尔": "女", "奥尔佳·达尼洛夫娜·特里波列娃": "女",
    "安玛": "女",
    "博士": "未知", "加西亚": "未知", "PRTS": "未知", "PCS系统主机": "未知",
    # 用戶指定（第三批）
    "考伯特": "男", "扎罗": "男", "卢比奥": "男", "文": "男",
    "孽茨雷": "男", "喀利喀": "男", "奎萨图什塔": "男",
    "坎诺特·古德英纳夫": "男", "寻路者信使": "男", "炎礼": "男",
    "马克·麦克斯": "男", "首言者": "男", "库林": "男",
    "科斯达": "男", "雷德": "男",
    '“保存者”': "男",
    "戈尔丁": "女", "贝尔德": "女", "阿尔贝塔": "女", "莫兰": "女",
    '“娜迦”': "女", '“圣徒”': "女", "托希娅": "女",
    "荣晚晴（老乡长）": "女", "阿斯帕齐娅": "女",
    '“影卫”': "未知", "引火的死魂灵": "未知", "幽灵": "未知",
    "屈光者": "未知", "瓦古": "未知", "梁": "未知",
    "零五四": "未知", "罗辛南特": "未知",
    "比丢": "未知", "六十七": "未知", "梅团 / 扬尼": "未知",
    "屠谕者": "未知", "宝宝": "未知", "科鲁兹": "未知",
    "米奥": "未知", "沃奥": "未知", "神明": "未知",
    '多利，“羊之主”': "男",
    '？？？': "男",
}


def load_operator_genders() -> dict[str, str]:
    """從幹員一覽 HTML 建立 name_hans → 性別 映射。"""
    global _operator_gender_cache
    if _operator_gender_cache:
        return _operator_gender_cache
    try:
        from bs4 import BeautifulSoup as _BS
        r = requests.get(f"{BASE_URL}/w/干员一览", headers=HEADERS, timeout=15)
        soup = _BS(r.text, "html.parser")
        result: dict[str, str] = {}
        for el in soup.find_all(attrs={"data-sex": True}):
            name = el.get("data-zh", "").strip()
            sex  = el.get("data-sex", "").strip()
            if name:
                result[name] = sex or "未知"
        result.update(GENDER_OVERRIDES)
        _operator_gender_cache = result
    except Exception:
        _operator_gender_cache = {}
    return _operator_gender_cache

# ── 泰拉地區資料 ─────────────────────────────────────────────────────────

TERRA_COUNTRIES: list[dict] = [
    # name: 繁體顯示名, en: 英文名, category: 分類
    # page: 萌娘百科頁面（簡體）, drive_prefixes: Drive 圖片前綴列表
    # first_image: 指定第一張圖片的 stem（無 .png），None 表示按字母順序
    # 現存國家
    {"name": "維多利亞", "en": "Victoria Empire",      "category": "現存國家", "page": "维多利亚(明日方舟)", "drive_prefixes": ["維多利亞"],           "first_image": "維多利亞-倫蒂尼姆",
     "image_order": ["維多利亞-倫蒂尼姆", "維多利亞-鄉村", "維多利亞-自救軍", "維多利亞-格拉斯哥幫", "維多利亞-綠意火花", "維多利亞-猩紅劇團"]},
    {"name": "烏薩斯",   "en": "Ursus Empire",         "category": "現存國家", "page": "乌萨斯",            "drive_prefixes": ["烏薩斯"],             "first_image": "烏薩斯-切爾諾伯格"},
    {"name": "卡西米爾", "en": "Kazimierz",             "category": "現存國家", "page": "卡西米尔",          "drive_prefixes": ["卡西米爾"],           "first_image": "卡西米爾-商業街",
     "image_order": ["卡西米爾-商業街", "卡西米爾-臨光家族", "卡西米爾-貴賓休息室", "卡西米爾-紅松騎士團"]},
    {"name": "拉特蘭",   "en": "Laterano",              "category": "現存國家", "page": "拉特兰",            "drive_prefixes": ["拉特蘭"],             "first_image": "拉特蘭"},
    {"name": "炎國",     "en": "Yan",                   "category": "現存國家", "page": "炎(明日方舟)",      "drive_prefixes": ["炎國"],               "first_image": "炎國-龍門",
     "image_order": ["炎國-龍門", "炎國-畫中世界", "炎國-尚蜀", "炎國-大荒城", "炎國-玉門", "炎國-龍門餐館"]},
    {"name": "東國",     "en": "Higashi",               "category": "現存國家", "page": "东国",      "drive_prefixes": ["東國"],               "first_image": None},
    {"name": "哥倫比亞", "en": "Columbia",              "category": "現存國家", "page": "哥伦比亚(明日方舟)", "drive_prefixes": ["哥倫比亞"],   "first_image": "哥倫比亞-特里蒙",
     "image_order": ["哥倫比亞-特里蒙", "哥倫比亞-萊茵生命1", "哥倫比亞-萊茵生命2", "哥倫比亞-冰釀的餐館", "哥倫比亞-咖啡館", "哥倫比亞-酒吧", "哥倫比亞-曼斯菲爾德監獄"]},
    {"name": "玻利瓦爾", "en": "Bolívar",               "category": "現存國家", "page": "玻利瓦尔",          "drive_prefixes": ["玻利維亞"],   "first_image": None},
    {"name": "萊塔尼亞", "en": "Leithanien",            "category": "現存國家", "page": "莱塔尼亚",          "drive_prefixes": ["萊塔尼亞"],   "first_image": None,
     "hardcoded_images": [
         "https://lh3.googleusercontent.com/d/19_wGDsODbB2OB-ob_uPdQea6YUT1X7oO",
     ]},
    {"name": "薩爾貢",   "en": "Sargon",                "category": "現存國家", "page": "萨尔贡",            "drive_prefixes": ["薩爾貢"],     "first_image": "薩爾貢",
     "hardcoded_images": [
         "https://lh3.googleusercontent.com/d/17qsu_flFfz2lhecPql_jko_KAt129flG",
         "https://lh3.googleusercontent.com/d/1wmSTXbtK7FPCOryPr8vZkhh4wFLgF-cf",
         "https://lh3.googleusercontent.com/d/1i7xWLRoJ_BvVa4oRXqRGYwfHdrPtviNe",
     ]},
    {"name": "薩米",     "en": "Sami",                  "category": "現存國家", "page": "萨米(明日方舟)",    "drive_prefixes": ["薩米"],       "first_image": "薩米-冰原",
     "hardcoded_images": [
         "https://lh3.googleusercontent.com/d/1QRiDNLDgQJf8W7ZXKgabbWINQjlKN7P8",
         "https://lh3.googleusercontent.com/d/1htrRznwbsJUrTR3smEddluj3KhHeGlvb",
     ]},
    {"name": "敘拉古",   "en": "Siracusa",              "category": "現存國家", "page": "叙拉古",            "drive_prefixes": ["敘拉古"],     "first_image": None},
    {"name": "米諾斯",   "en": "Minos",                 "category": "現存國家", "page": "米诺斯(明日方舟)",  "drive_prefixes": ["米諾斯"],     "first_image": None},
    {"name": "伊比利亞", "en": "Iberia",                "category": "現存國家", "page": "伊比利亚",          "drive_prefixes": ["伊比利亞"],   "first_image": "伊比利亞"},
    {"name": "謝拉格",   "en": "Kjerag",                "category": "現存國家", "page": "谢拉格",  "drive_prefixes": ["謝拉格"],     "first_image": "謝拉格-雪山",
     "hardcoded_images": [
         "https://lh3.googleusercontent.com/d/130P4gsooxsfA_6aLk4JbDk26TOT6guET",
         "https://lh3.googleusercontent.com/d/19iACRmOC9EighdQYoc7InZZQMUL4uh0a",
     ]},
    {"name": "雷姆必拓", "en": "Rim Billiton",          "category": "現存國家", "page": "雷姆必拓",          "drive_prefixes": ["雷姆必拓"],   "first_image": "雷姆必拓",
     "hardcoded_images": [
         "https://lh3.googleusercontent.com/d/1skQjR1xJ9Qm8voXwvAXDSEb6C52TCa3T",
         "https://lh3.googleusercontent.com/d/1fbeZ7OI0JBRwOE4EWASk1k5xy5dppyPy",
     ]},
    {"name": "卡茲戴爾", "en": "Kazdel",                "category": "現存國家", "page": "卡兹戴尔",          "drive_prefixes": ["卡茲戴爾"],   "first_image": None},
    {"name": "阿戈爾",   "en": "Aegir",                 "category": "現存國家", "page": "阿戈尔",  "drive_prefixes": ["阿戈爾"],     "first_image": None,
     "hardcoded_images": [
         "https://lh3.googleusercontent.com/d/1sJmEAl56X0zw2SdH4aKdkiR4DKJctYgw",
     ]},
    # 獨立城市
    {"name": "汐斯塔",   "en": "Siesta",                "category": "獨立城市", "page": "汐斯塔",            "drive_prefixes": ["汐斯塔"],     "first_image": None},
    # 歷史國家
    {"name": "高盧",     "en": "Gaul",                  "category": "歷史國家", "page": "高卢(明日方舟)",    "drive_prefixes": ["高盧"],       "first_image": None},
]

_drive_image_cache: dict[str, str] = {}   # stem (無 .png) → lh3.googleusercontent URL
_terra_data_cache:  dict[str, dict] = {}  # Moegirl page name → {intro, emblem_url}


def load_drive_images() -> dict[str, str]:
    """抓取 Google Drive 資料夾，建立 filename_stem → 直連 URL 映射。"""
    global _drive_image_cache
    if _drive_image_cache:
        return _drive_image_cache
    try:
        r = requests.get(
            "https://drive.google.com/drive/folders/1Vl9mb0XkQp1OBL-n35qEUNxqKBrs2R0f",
            headers=HEADERS, timeout=20,
        )
        pattern = r'aria-label="([^"]+\.png)[^"]*"[^>]*>.*?"(1[A-Za-z0-9_-]{32,33})"'
        seen: set[str] = set()
        result: dict[str, str] = {}
        for name, fid in re.findall(pattern, r.text, re.DOTALL):
            stem = name.removesuffix(".png")
            if stem not in seen:
                result[stem] = f"https://lh3.googleusercontent.com/d/{fid}"
                seen.add(stem)
        _drive_image_cache = result
    except Exception:
        _drive_image_cache = {}
    return _drive_image_cache


def _fetch_terra_country_data(page: str) -> dict:
    """抓取萌娘百科地區頁面的簡介與國徽 URL（有快取）。"""
    if page in _terra_data_cache:
        return _terra_data_cache[page]

    from urllib.parse import quote as _quote
    from bs4 import BeautifulSoup

    data: dict = {"intro": "", "emblem_url": ""}
    try:
        r = requests.get(
            f"https://zh.moegirl.org.cn/zh-tw/{_quote(page)}",
            headers=HEADERS, timeout=15,
        )
        soup = BeautifulSoup(r.text, "html.parser")

        # 簡介：h2#简介 → 父 div → 往後找 <p>，用 regex 取文字（頁面用 TemplateString）
        intro_parts: list[str] = []
        h2 = soup.find("h2", id="简介")
        if h2:
            sibling = h2.parent.find_next_sibling()
            while sibling:
                if sibling.name == "div" and "mw-heading" in (sibling.get("class") or []):
                    break
                if sibling.name == "p":
                    raw = re.sub(r"<br\s*/?>", "\n", str(sibling), flags=re.IGNORECASE)
                    t = re.sub(r"<[^>]+>", "", raw)
                    t = re.sub(r"\[\d+\]", "", t).strip()
                    if len(t) >= 20:
                        intro_parts.append(t)
                sibling = sibling.find_next_sibling()
        data["intro"] = "\n".join(intro_parts[:3])

        # 國徽：div.moe-infobox → span.infobox-image → img
        infobox = soup.find("div", class_="moe-infobox")
        if infobox:
            img_span = infobox.find("span", class_="infobox-image")
            img = img_span.find("img") if img_span else infobox.find("img")
            if img:
                src = img.get("src", "")
                if src.startswith("//"):
                    src = "https:" + src
                data["emblem_url"] = src.split("!/")[0]
    except Exception:
        pass

    _terra_data_cache[page] = data
    return data


def search_terra_countries(query: str) -> list[str]:
    """自動完成：回傳符合查詢的地區名稱（最多 25 筆）。"""
    q = zhconv.convert(query, "zh-hans").lower()
    return [
        c["name"] for c in TERRA_COUNTRIES
        if q in zhconv.convert(c["name"], "zh-hans").lower()
        or q in c["en"].lower()
    ][:25]


def get_terra_country(query: str) -> dict | None:
    """依地區名稱（繁簡英均可）查詢地區資料，含簡介、國徽與 Drive 圖片 URL 列表。"""
    q = zhconv.convert(query, "zh-hans").lower()
    for c in TERRA_COUNTRIES:
        name_hans = zhconv.convert(c["name"], "zh-hans").lower()
        if q == name_hans or q in name_hans or q in c["en"].lower():
            moegirl = _fetch_terra_country_data(c["page"])

            if c.get("hardcoded_images"):
                image_urls = c["hardcoded_images"]
            else:
                drive = load_drive_images()
                imgs: dict[str, str] = {}
                for prefix in c["drive_prefixes"]:
                    for stem, url in drive.items():
                        if stem.startswith(prefix):
                            imgs[stem] = url
                if c.get("image_order"):
                    ordered = [k for k in c["image_order"] if k in imgs]
                    ordered += sorted(k for k in imgs if k not in c["image_order"])
                else:
                    first = c.get("first_image")
                    if first and first in imgs:
                        ordered = [first] + sorted(k for k in imgs if k != first)
                    else:
                        ordered = sorted(imgs.keys())
                image_urls = [imgs[k] for k in ordered]

            return {
                "name":       c["name"],
                "en":         c["en"],
                "category":   c["category"],
                "intro":      moegirl["intro"],
                "emblem_url": moegirl["emblem_url"],
                "image_urls": image_urls,
            }
    return None


def load_story_chars() -> list[dict]:
    """載入泰拉大典:角色/其他 + 剧情角色一览，只保留有立繪的角色。"""
    global _story_char_cache
    if _story_char_cache:
        return _story_char_cache

    from bs4 import BeautifulSoup as _BS

    result: list[dict] = []
    seen: set[str] = set()

    # ── 來源一：泰拉大典:角色/其他 ──────────────────────────────────────────
    r = requests.get(
        "https://prts.wiki/w/泰拉大典:角色/其他",
        headers=HEADERS, timeout=20,
    )
    soup = _BS(r.text, "html.parser")

    for t in soup.find_all("table"):
        name_th = t.find("th", attrs={"colspan": "5"})
        if not name_th:
            continue
        name = name_th.get_text().strip()
        if not name:
            continue

        tabber = t.find("div", class_="tabber")
        if not tabber:
            continue
        imgs = tabber.find_all("img")
        if not imgs:
            continue

        name_hans = zhconv.convert(name, "zh-hans")
        key = name_hans.lower()
        if key in seen:
            continue
        seen.add(key)

        image_urls: list[str] = []
        for img in imgs:
            src = img.get("src", "")
            full = re.sub(
                r"(https://media\.prts\.wiki)/thumb(/[^/]+/[^/]+/[^/]+\.png)/.*",
                r"\1\2", src,
            )
            if full and full.startswith("http"):
                image_urls.append(full)

        intro = ""
        intro_th = t.find("th", string=re.compile("角色经历"))
        if intro_th:
            intro_td = intro_th.find_next("td")
            if intro_td:
                raw = re.sub(r"<br\s*/?>", "\n", str(intro_td), flags=re.IGNORECASE)
                intro = re.sub(r"<[^>]+>", "", raw).strip()[:800]

        if name_hans not in GENDER_OVERRIDES:
            continue
        gender = GENDER_OVERRIDES[name_hans]

        result.append({
            "name_hans": name_hans,
            "name_trad": zhconv.convert(name, "zh-hant"),
            "intro_trad": zhconv.convert(intro, "zh-hant"),
            "source_trad": "",
            "gender": gender,
            "image_urls": image_urls,
        })

    # ── 來源二：剧情角色一览 ─────────────────────────────────────────────────
    try:
        r2 = requests.get(
            "https://prts.wiki/w/剧情角色一览",
            headers=HEADERS, timeout=30,
        )
        soup2 = _BS(r2.text, "html.parser")

        for t in soup2.find_all("table", class_="wikitable"):
            if not t.find("th", attrs={"colspan": "4"}):
                continue
            for tr in t.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) < 4:
                    continue
                if "通用立绘" in tds[3].get_text():
                    continue
                name_a = tds[0].find("a")
                name = name_a.get_text().strip() if name_a else tds[0].get_text().strip()
                if not name:
                    continue
                name_hans = zhconv.convert(name, "zh-hans")
                key = name_hans.lower()
                if key in seen:
                    continue
                imgs = tds[3].find_all("img")
                if not imgs:
                    continue
                seen.add(key)

                image_urls = []
                for img in imgs:
                    src = img.get("src", "")
                    full = re.sub(
                        r"(https://media\.prts\.wiki)/thumb(/[^/]+/[^/]+/[^/]+\.png)/.*",
                        r"\1\2", src,
                    )
                    if full and full.startswith("http"):
                        image_urls.append(full)
                image_urls = list(dict.fromkeys(image_urls))
                if not image_urls:
                    continue

                raw = re.sub(r"<br\s*/?>", "\n", str(tds[1]), flags=re.IGNORECASE)
                intro = re.sub(r"<[^>]+>", "", raw).strip()[:800]
                source = tds[2].get_text().strip()
                if name_hans not in GENDER_OVERRIDES:
                    continue
                gender = GENDER_OVERRIDES[name_hans]

                result.append({
                    "name_hans": name_hans,
                    "name_trad": zhconv.convert(name, "zh-hant"),
                    "intro_trad": zhconv.convert(intro, "zh-hant"),
                    "source_trad": zhconv.convert(source, "zh-hant"),
                    "gender": gender,
                    "image_urls": image_urls,
                })
    except Exception:
        pass

    _story_char_cache = result
    return result


def search_story_chars(query: str) -> list[str]:
    """自動完成：回傳符合查詢的劇情角色名稱（繁體，最多 25 筆）。"""
    q = zhconv.convert(query, "zh-hans").lower()
    chars = load_story_chars()
    return [c["name_trad"] for c in chars if q in c["name_hans"].lower()][:25]


def get_story_char(query: str) -> dict | None:
    """依名稱查詢劇情角色（繁簡均可），回傳角色資料。"""
    q = zhconv.convert(query, "zh-hans").lower()
    for c in load_story_chars():
        if q == c["name_hans"].lower() or q in c["name_hans"].lower():
            return c
    return None


def get_gacha_pools() -> list[dict]:
    """從卡池一覽擷取限時尋訪列表，由新至舊。"""
    try:
        r = requests.get(
            f"{BASE_URL}/api.php",
            params={
                "action": "parse",
                "page": "卡池一览",
                "prop": "wikitext",
                "format": "json",
            },
            headers=HEADERS,
            timeout=15,
        )
        wt = r.json().get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        return []

    section_m = re.search(r"==限时寻访==(.*?)(?=\n==|\Z)", wt, re.DOTALL)
    if not section_m:
        return []

    pools: list[dict] = []
    for row in _table_rows(section_m.group(1)):
        cells = _row_cells(row)
        if len(cells) < 3:
            continue

        # 欄位 0：尋訪名稱（排除圖片連結）
        name_m = re.search(r"\[\[(?!文件:)([^\]|]+)(?:\|([^\]]+))?\]\]", cells[0])
        if not name_m:
            continue
        pool_name = (name_m.group(2) or name_m.group(1)).strip()

        # 欄位 1：開始時間
        time_m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})~", cells[1])
        if not time_m:
            continue

        # 欄位 2：6★ 幹員
        ops_6 = [
            zhconv.convert(op.strip(), "zh-hant")
            for op in re.findall(r"\{\{干员头像\|([^|}]+)", cells[2])
        ]

        # 欄位 3：5★/4★ 幹員
        ops_other: list[str] = []
        if len(cells) > 3:
            ops_other = [
                zhconv.convert(op.strip(), "zh-hant")
                for op in re.findall(r"\{\{干员头像\|([^|}]+)", cells[3])
            ]

        pools.append(
            {
                "name": zhconv.convert(pool_name, "zh-hant"),
                "start_time": time_m.group(1),
                "ops_6": ops_6,
                "ops_other": ops_other,
            }
        )

    return pools


def load_wikig_operators() -> list[str]:
    """從 wiki.gg Category:Operators 取得所有幹員英文名稱列表。"""
    global _wikig_op_cache
    if _wikig_op_cache:
        return _wikig_op_cache
    try:
        params = {
            "action": "query", "list": "categorymembers",
            "cmtitle": "Category:Operator", "cmlimit": 500,
            "cmnamespace": 0, "format": "json",
        }
        r = requests.get(f"{WIKIG_BASE}/api.php", params=params,
                         headers=WIKIG_HEADERS, timeout=15)
        _wikig_op_cache = [
            m["title"] for m in r.json()["query"]["categorymembers"]
            if "/" not in m["title"]
        ]
    except Exception:
        _wikig_op_cache = []
    return _wikig_op_cache


# 無法透過 PRTS redirect 自動找到的幹員，手動補充
_WIKIG_CN_SUPPLEMENTS: dict[str, str] = {
    "Shirayuki": "白雪",
    "Reed the Flame Shadow": "焰影葦草",
    "Lava the Purgatory": "炎獄炎熔",
    "Leto": "露託",
    "Pozëmka": "寒霜",
    "Snegurochka": "雪獵",
    "Vetochki": "折椏",
    "Rosa": "早露",
    "Mr. Nothing": "烏有",
    "Fang the Fire-Sharpened": "歷陣銳槍芬",
    "Lessing": "止頌",
}


def load_wikig_cn_names() -> dict[str, str]:
    """透過 PRTS redirect 建立 wiki.gg 英文名 → 繁體中文名對應表（小寫 key）。"""
    global _wikig_cn_cache
    if _wikig_cn_cache:
        return _wikig_cn_cache
    ops = load_wikig_operators()
    if not ops:
        return _wikig_cn_cache
    result: dict[str, str] = {}
    batch_size = 50
    for i in range(0, len(ops), batch_size):
        batch = ops[i : i + batch_size]
        try:
            params = {
                "action": "query",
                "titles": "|".join(batch),
                "redirects": 1,
                "format": "json",
            }
            r = requests.get(f"{BASE_URL}/api.php", params=params,
                             headers=HEADERS, timeout=15)
            data = r.json().get("query", {})
            # 重新導向：wiki.gg 英文名 → PRTS 簡體中文名
            redirects: dict[str, str] = {
                rd["from"].lower(): rd["to"]
                for rd in data.get("redirects", [])
            }
            # 正規化對應：PRTS 查詢後的最終頁面標題（含直接頁面和重新導向目標）
            page_titles: dict[str, str] = {}
            for page in data.get("pages", {}).values():
                if "missing" not in page:
                    page_titles[page["title"].lower()] = page["title"]
            for en in batch:
                en_low = en.lower()
                # 情況 1：有重新導向（英文名 → 中文名）
                hans = redirects.get(en_low)
                # 情況 2：直接存在（頁面名稱就是英文，如 Mon3tr / 12F）
                if not hans and en_low in page_titles:
                    hans = page_titles[en_low]
                if hans:
                    cn_trad = zhconv.convert(hans, "zh-hant")
                    result[en_low] = cn_trad
                    result[en_low.replace(" ", "")] = cn_trad
        except Exception:
            pass
    # 補充表強制覆蓋（優先於自動查詢結果）
    for en, cn in _WIKIG_CN_SUPPLEMENTS.items():
        result[en.lower()] = cn
        result[en.lower().replace(" ", "")] = cn
    _wikig_cn_cache = result
    return _wikig_cn_cache


def _get_wikig_voice_urls(op_name: str) -> list[str]:
    """透過 wiki.gg MediaWiki API 取得幹員所有 JP 語音 URL（快取）。"""
    if op_name in _wikig_voice_url_cache:
        return _wikig_voice_url_cache[op_name]
    url_name = op_name.replace(" ", "_")
    titles = "|".join(f"File:{url_name}-{i:03d}.ogg" for i in range(1, 51))
    try:
        r = requests.get(
            f"{WIKIG_BASE}/api.php",
            params={"action": "query", "titles": titles,
                    "prop": "imageinfo", "iiprop": "url", "format": "json"},
            headers=WIKIG_HEADERS, timeout=15,
        )
        pages = r.json().get("query", {}).get("pages", {}).values()
        urls = [
            p["imageinfo"][0]["url"]
            for p in pages
            if "missing" not in p and p.get("imageinfo")
        ]
    except Exception:
        urls = []
    _wikig_voice_url_cache[op_name] = urls
    return urls


def get_wikig_random_voice(op_name: str) -> bytes | None:
    """下載幹員隨機一條 JP 語音，回傳 bytes；失敗回傳 None。"""
    urls = _get_wikig_voice_urls(op_name)
    if not urls:
        return None
    for _ in range(3):
        url = random.choice(urls)
        try:
            r = requests.get(url, headers=WIKIG_HEADERS, timeout=10)
            if r.status_code == 200 and len(r.content) > 5000:
                return r.content
        except Exception:
            pass
    return None


def _get_wikig_fixed_voice(op_name: str, number: str) -> bytes | None:
    url_name = op_name.replace(" ", "_")
    url = f"{WIKIG_BASE}/images/{url_name}-{number}.ogg"
    try:
        r = requests.get(url, headers=WIKIG_HEADERS, timeout=10)
        if r.status_code == 200 and len(r.content) > 5000:
            return r.content
    except Exception:
        pass
    return None


def get_wikig_title_voice(op_name: str) -> bytes | None:
    """下載幹員 Title 語音（第 035 條 JP）。"""
    return _get_wikig_fixed_voice(op_name, "035")


def get_wikig_tap_voice(op_name: str) -> bytes | None:
    """下載幹員 Tap 語音（第 032 條 JP）。"""
    return _get_wikig_fixed_voice(op_name, "032")
