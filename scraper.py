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
_file_url_cache: dict[str, str] = {}
_image_urls_cache: dict[str, dict] = {}


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


def get_wife_image(hans_name: str) -> tuple[str, str]:
    """回傳 (繁體名稱, 立繪URL)，優先精二，次選精零。"""
    trad = zhconv.convert(hans_name, "zh-hant")
    url = _get_file_url(f"立绘_{hans_name}_2.png")
    if not url:
        url = _get_file_url(f"立绘_{hans_name}_1.png")
    return trad, url


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
