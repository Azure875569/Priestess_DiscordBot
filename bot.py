import asyncio
import io
import json
import os
from typing import Optional
import discord
import zhconv
from discord import app_commands
from dotenv import load_dotenv
import random
from scraper import get_operator_data, get_skill_data, get_material_data, get_lore_data, get_skin_data, get_gacha_pools, get_all_operator_names, get_wife_image, get_real_name, search_real_names, load_real_names, load_operator_names, load_range_data, render_range, search_operator_names, RARITY_STARS, IS_CONFIGS, get_is_difficulty, get_is_squads, get_is_relic, search_is_relic_names, load_story_chars, search_story_chars, get_story_char, search_terra_countries, get_terra_country, load_drive_images, load_operator_genders, PORTRAIT_INDEX_OVERRIDES, load_wikig_operators, get_wikig_random_voice, get_wikig_title_voice, get_wikig_tap_voice, load_wikig_cn_names

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

RARITY_COLORS = {
    "1": 0x808080,
    "2": 0x1EAD2C,
    "3": 0x0099FF,
    "4": 0x9B59B6,
    "5": 0xFFD700,
    "6": 0xFF6A00,
}

def _fi(value: str, limit: int = 10) -> bool:
    """值夠短才 inline，避免欄位內換行。"""
    return len(value) <= limit


intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def _fmt_mat(items: list[tuple[str, str]]) -> str:
    """將材料列表格式化為易讀字串。"""
    return "、".join(f"{n}×{q}" for n, q in items) if items else "暫無資料"


class SkinView(discord.ui.View):
    """每頁一套時裝，用左右箭頭切換，超過一套才顯示按鈕。"""

    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.current = 0
        self._build()

    def _build(self) -> None:
        self.clear_items()
        if len(self.embeds) > 1:
            prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=0)
            prev.callback = self._prev
            self.add_item(prev)
            nxt = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=0)
            nxt.callback = self._next
            self.add_item(nxt)
        del_btn = discord.ui.Button(label="🗑️", style=discord.ButtonStyle.danger, row=1)
        del_btn.callback = self._delete
        self.add_item(del_btn)

    async def _prev(self, interaction: discord.Interaction):
        self.current = (self.current - 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.current], view=self)

    async def _next(self, interaction: discord.Interaction):
        self.current = (self.current + 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.current], view=self)

    async def _delete(self, interaction: discord.Interaction):
        await interaction.message.delete()


class LoreView(discord.ui.View):
    def __init__(self, pages: list[tuple[str, discord.Embed]]):
        super().__init__(timeout=180)
        self.pages = pages
        self.current = 0
        self._build()

    def _build(self) -> None:
        self.clear_items()
        select = discord.ui.Select(
            placeholder=f"📖 {self.pages[self.current][0]}",
            options=[
                discord.SelectOption(
                    label=f"{i + 1}. {label}",
                    value=str(i),
                    default=(i == self.current),
                )
                for i, (label, _) in enumerate(self.pages)
            ],
            row=0,
        )
        select.callback = self._on_select
        self.add_item(select)
        del_btn = discord.ui.Button(label="🗑️", style=discord.ButtonStyle.danger, row=1)
        del_btn.callback = self._delete
        self.add_item(del_btn)

    async def _on_select(self, interaction: discord.Interaction):
        self.current = int(interaction.data["values"][0])
        self._build()
        await interaction.response.edit_message(embed=self.pages[self.current][1], view=self)

    async def _delete(self, interaction: discord.Interaction):
        await interaction.message.delete()


class MaterialView(discord.ui.View):
    def __init__(self, pages: list[tuple[str, discord.Embed]]):
        super().__init__(timeout=180)
        self.pages = pages
        self.current = 0
        self._build()

    def _build(self) -> None:
        self.clear_items()
        for i, (label, _) in enumerate(self.pages):
            style = discord.ButtonStyle.primary if i == self.current else discord.ButtonStyle.secondary
            btn = discord.ui.Button(label=label, style=style, row=0)
            btn.callback = self._make_cb(i)
            self.add_item(btn)
        del_btn = discord.ui.Button(label="🗑️", style=discord.ButtonStyle.danger, row=1)
        del_btn.callback = self._delete
        self.add_item(del_btn)

    def _make_cb(self, index: int):
        async def cb(interaction: discord.Interaction):
            self.current = index
            self._build()
            await interaction.response.edit_message(embed=self.pages[index][1], view=self)
        return cb

    async def _delete(self, interaction: discord.Interaction):
        await interaction.message.delete()


class SkillView(discord.ui.View):
    def __init__(self, pages: list[tuple[str, discord.Embed]], num_skills: int = 0):
        super().__init__(timeout=180)
        self.pages = pages
        self.num_skills = num_skills  # 技能按鈕放 row 0，其餘放 row 1
        self.current = 0
        self._build()

    def _build(self) -> None:
        self.clear_items()
        for i, (label, _) in enumerate(self.pages):
            row = 0 if i < self.num_skills else 1
            style = discord.ButtonStyle.primary if i == self.current else discord.ButtonStyle.secondary
            btn = discord.ui.Button(label=label, style=style, row=row)
            btn.callback = self._make_cb(i)
            self.add_item(btn)
        del_btn = discord.ui.Button(label="🗑️", style=discord.ButtonStyle.danger, row=2)
        del_btn.callback = self._delete
        self.add_item(del_btn)

    def _make_cb(self, index: int):
        async def cb(interaction: discord.Interaction):
            self.current = index
            self._build()
            await interaction.response.edit_message(embed=self.pages[index][1], view=self)
        return cb

    async def _delete(self, interaction: discord.Interaction):
        await interaction.message.delete()


class ISInfoView(discord.ui.View):
    """集成戰略難度/分隊資訊分頁 View。"""

    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.idx = 0
        self._sync()

    def _sync(self):
        self.prev_btn.disabled = self.idx == 0
        self.next_btn.disabled = self.idx >= len(self.embeds) - 1

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.idx -= 1
        self._sync()
        await interaction.response.edit_message(embed=self.embeds[self.idx], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.idx += 1
        self._sync()
        await interaction.response.edit_message(embed=self.embeds[self.idx], view=self)

    @discord.ui.button(label="🗑️", style=discord.ButtonStyle.danger, row=0)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()


class DeleteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="🗑️", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()


class OperatorView(discord.ui.View):
    def __init__(self, embed1: discord.Embed, embed2: discord.Embed, images: list[tuple[str, str]]):
        super().__init__(timeout=180)
        self.embed1 = embed1
        self.embed2 = embed2
        self.images = images
        self._img_btns: list[discord.ui.Button] = []
        self._build_page1()

    def _build_page1(self) -> None:
        self.clear_items()
        self._img_btns = []
        for i, (label, _) in enumerate(self.images):
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary if i == 0 else discord.ButtonStyle.secondary,
                row=0,
            )
            btn.callback = self._make_img_callback(i)
            self.add_item(btn)
            self._img_btns.append(btn)
        nav = discord.ui.Button(label="屬性・潛能 ▶", style=discord.ButtonStyle.secondary, row=1)
        nav.callback = self._go_page2
        self.add_item(nav)
        self._add_delete_btn(row=1)

    def _build_page2(self) -> None:
        self.clear_items()
        nav = discord.ui.Button(label="◀ 基本資料", style=discord.ButtonStyle.secondary)
        nav.callback = self._go_page1
        self.add_item(nav)
        self._add_delete_btn(row=0)

    def _add_delete_btn(self, row: int) -> None:
        btn = discord.ui.Button(label="🗑️", style=discord.ButtonStyle.danger, row=row)
        btn.callback = self._delete
        self.add_item(btn)

    async def _delete(self, interaction: discord.Interaction) -> None:
        await interaction.message.delete()

    def _make_img_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            _, url = self.images[index]
            self.embed1.set_image(url=url)
            for i, btn in enumerate(self._img_btns):
                btn.style = discord.ButtonStyle.primary if i == index else discord.ButtonStyle.secondary
            await interaction.response.edit_message(embed=self.embed1, view=self)
        return callback

    async def _go_page2(self, interaction: discord.Interaction) -> None:
        self._build_page2()
        await interaction.response.edit_message(embed=self.embed2, view=self)

    async def _go_page1(self, interaction: discord.Interaction) -> None:
        self._build_page1()
        await interaction.response.edit_message(embed=self.embed1, view=self)


async def operator_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    results = await asyncio.to_thread(search_operator_names, current)
    return [
        app_commands.Choice(name=zhconv.convert(name, "zh-hant"), value=name)
        for name in results
    ]


async def real_name_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    results = await asyncio.to_thread(search_real_names, current)
    return [app_commands.Choice(name=name, value=name) for name in results]


@tree.command(name="角色真名", description="查詢明日方舟角色的真實姓名與出處")
@app_commands.describe(角色名稱="輸入角色代號，例如：銀灰、能天使、德克薩斯")
@app_commands.autocomplete(角色名稱=real_name_autocomplete)
async def operator_real_name(interaction: discord.Interaction, 角色名稱: str):
    await interaction.response.defer(thinking=True)
    try:
        data = await asyncio.to_thread(get_real_name, 角色名稱)
        if not data:
            await interaction.followup.send(embed=discord.Embed(
                description=f"❌ 找不到「{角色名稱}」的真名資料，或該角色真名未公開。",
                color=0xFF0000,
            ))
            return

        category = "羅德島幹員" if data["is_operator"] else "其他角色"
        em = discord.Embed(
            title=data["codename"],
            description=f"*{category}*",
            color=0x5865F2 if data["is_operator"] else 0x808080,
            url="https://prts.wiki/w/角色真名",
        )
        em.add_field(name="真名", value=data["real_name"] or "（未公開）", inline=False)
        em.add_field(name="出處", value=data["source"] or "—", inline=False)
        if data["avatar_url"]:
            em.set_thumbnail(url=data["avatar_url"])
        em.set_footer(text="資料來源：PRTS Wiki・角色真名")
        await interaction.followup.send(embed=em, view=DeleteView())
    except Exception:
        await interaction.followup.send("❌ 處理時發生錯誤，請稍後再試。", ephemeral=True)


_IS_HANS_NAMES = list(IS_CONFIGS.keys())
_RELIC_RARITY_LABEL = {0: "普通", 1: "高級", 2: "精英", 3: "傳說"}
_RELIC_RARITY_COLOR = {0: 0x888888, 1: 0x6699FF, 2: 0xFFCC00, 3: 0xFF6644}


async def is_name_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    current_hans = zhconv.convert(current, "zh-hans")
    matches = [k for k in _IS_HANS_NAMES if current_hans in k or current_hans in zhconv.convert(k, "zh-hant")]
    return [
        app_commands.Choice(name=IS_CONFIGS[k]["trad"], value=k)
        for k in matches[:25]
    ]


async def is_relic_name_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    is_name_hans = getattr(interaction.namespace, "集成戰略名稱", None) or ""
    if not is_name_hans or is_name_hans not in IS_CONFIGS:
        return []
    results = await asyncio.to_thread(search_is_relic_names, is_name_hans, current)
    return [app_commands.Choice(name=n, value=n) for n in results]


@tree.command(name="集成戰略資訊", description="查詢集成戰略的難度資料、分隊介紹或特定藏品資訊")
@app_commands.describe(
    集成戰略名稱="選擇集成戰略，例如：薩卡茲的無終奇語、歲的界園志異",
    資訊類型="選擇資訊種類",
    藏品名稱="查詢「藏品資訊」時填入藏品名稱",
)
@app_commands.choices(資訊類型=[
    app_commands.Choice(name="難度資料", value="難度資料"),
    app_commands.Choice(name="分隊介紹", value="分隊介紹"),
    app_commands.Choice(name="藏品資訊", value="藏品資訊"),
])
@app_commands.autocomplete(集成戰略名稱=is_name_autocomplete, 藏品名稱=is_relic_name_autocomplete)
async def is_info(
    interaction: discord.Interaction,
    集成戰略名稱: str,
    資訊類型: str,
    藏品名稱: str = "",
):
    await interaction.response.defer(thinking=True)
    is_hans = 集成戰略名稱
    cfg = IS_CONFIGS.get(is_hans, {})
    if not cfg:
        await interaction.followup.send("❌ 找不到該集成戰略，請透過自動完成選單選取。", ephemeral=True)
        return

    is_trad = cfg["trad"]
    is_wiki_url = f"https://prts.wiki/w/{is_hans}"

    # ── 難度資料 ──────────────────────────────────────────────────────
    if 資訊類型 == "難度資料":
        if cfg["num"] == 1:
            await interaction.followup.send("❌ 刻俄柏的灰蕈迷境不提供難度資料。", ephemeral=True)
            return
        data = await asyncio.to_thread(get_is_difficulty, is_hans)
        if not data:
            await interaction.followup.send("❌ 無法取得難度資料，請稍後再試。", ephemeral=True)
            return

        # 每頁顯示 7 筆
        page_size = 7
        pages = []
        for i in range(0, len(data), page_size):
            chunk = data[i : i + page_size]
            em = discord.Embed(
                title=f"{is_trad} — 難度資料",
                color=0x5B8DD9,
                url=is_wiki_url,
            )
            lines = []
            for d in chunk:
                lv = f"Lv.{d['level']}" if d["level"] else ""
                score = f"  `{d['score']}`" if d["score"] else ""
                lines.append(f"**{zhconv.convert(d['name'], 'zh-hant')}** {lv}{score}")
                if d["conditions"]:
                    lines.append(f"> {zhconv.convert(d['conditions'], 'zh-hant')}")
            em.description = "\n".join(lines)
            em.set_footer(text=f"第 {i//page_size + 1}/{-(-len(data)//page_size)} 頁｜資料來源：PRTS Wiki")
            pages.append(em)

        view = ISInfoView(pages) if len(pages) > 1 else DeleteView()
        await interaction.followup.send(embed=pages[0], view=view)

    # ── 分隊介紹 ──────────────────────────────────────────────────────
    elif 資訊類型 == "分隊介紹":
        data = await asyncio.to_thread(get_is_squads, is_hans)
        if not data:
            await interaction.followup.send("❌ 無法取得分隊資料，請稍後再試。", ephemeral=True)
            return

        page_size = 5
        pages = []
        for i in range(0, len(data), page_size):
            chunk = data[i : i + page_size]
            em = discord.Embed(
                title=f"{is_trad} — 分隊介紹",
                color=0x2ECC71,
                url=is_wiki_url,
            )
            for s in chunk:
                val = s["effect"] or "（無效果說明）"
                if s["unlock"]:
                    val += f"\n解鎖：{s['unlock']}"
                em.add_field(name=s["name"], value=val[:400], inline=False)
            em.set_footer(text=f"第 {i//page_size + 1}/{-(-len(data)//page_size)} 頁｜資料來源：PRTS Wiki")
            pages.append(em)

        view = ISInfoView(pages) if len(pages) > 1 else DeleteView()
        await interaction.followup.send(embed=pages[0], view=view)

    # ── 藏品資訊 ──────────────────────────────────────────────────────
    elif 資訊類型 == "藏品資訊":
        if not 藏品名稱:
            await interaction.followup.send("❌ 請輸入藏品名稱（可使用自動完成搜尋）。", ephemeral=True)
            return
        relic = await asyncio.to_thread(get_is_relic, is_hans, 藏品名稱)
        if not relic:
            await interaction.followup.send(f"❌ 在「{is_trad}」中找不到藏品「{藏品名稱}」。", ephemeral=True)
            return

        rarity = relic["rarity"]
        color = _RELIC_RARITY_COLOR.get(rarity, 0x888888)
        rarity_label = _RELIC_RARITY_LABEL.get(rarity, "")
        stars = "★" * (rarity + 1)

        em = discord.Embed(
            title=relic["name_trad"],
            description=f"{stars}  {rarity_label}　　售價：{relic['price'] or '—'}",
            color=color,
            url=is_wiki_url,
        )
        em.add_field(name="效果", value=relic["effect"] or "—", inline=False)
        if relic["description"]:
            em.add_field(name="描述", value=relic["description"], inline=False)
        em.set_footer(text=f"資料來源：PRTS Wiki・{is_trad}")
        await interaction.followup.send(embed=em, view=DeleteView())


async def terra_country_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    results = await asyncio.to_thread(search_terra_countries, current)
    return [app_commands.Choice(name=n, value=n) for n in results]


@tree.command(name="地區資料", description="查詢明日方舟泰拉大陸地區的簡介、國徽與場景圖")
@app_commands.describe(地區名稱="輸入地區名稱，例如：維多利亞、炎國、卡西米爾")
@app_commands.autocomplete(地區名稱=terra_country_autocomplete)
async def terra_country_cmd(interaction: discord.Interaction, 地區名稱: str):
    await interaction.response.defer(thinking=True)
    try:
        data = await asyncio.to_thread(get_terra_country, 地區名稱)
        if not data:
            await interaction.followup.send(f"❌ 找不到地區「{地區名稱}」。", ephemeral=True)
            return

        embeds: list[discord.Embed] = []

        # 第一頁：文字資訊 + 第一張場景圖
        intro = data["intro"][:1480] or "（暫無簡介資料）"
        em = discord.Embed(
            title=data["name"],
            description=f"*{data['en']}*\n\n{intro}",
            color=0x4A7FA5,
        )
        if data["emblem_url"]:
            em.set_thumbnail(url=data["emblem_url"])
        if data["image_urls"]:
            em.set_image(url=data["image_urls"][0])
        total = len(data["image_urls"])
        page_info = f"圖片 1/{total} | " if total else ""
        em.set_footer(text=f"{page_info}資料來源：萌娘百科 | 圖片：網頁活動-泰拉尋旅")
        embeds.append(em)

        # 後續頁：其餘場景圖（保留文字內容）
        for i, img_url in enumerate(data["image_urls"][1:], 2):
            em_img = discord.Embed(
                title=data["name"],
                description=f"*{data['en']}*\n\n{intro}",
                color=0x4A7FA5,
            )
            if data["emblem_url"]:
                em_img.set_thumbnail(url=data["emblem_url"])
            em_img.set_image(url=img_url)
            em_img.set_footer(text=f"圖片 {i}/{total} | 資料來源：萌娘百科 | 圖片：網頁活動-泰拉尋旅")
            embeds.append(em_img)

        view = ISInfoView(embeds) if len(embeds) > 1 else DeleteView()
        await interaction.followup.send(embed=embeds[0], view=view)

    except Exception:
        await interaction.followup.send("❌ 處理時發生錯誤，請稍後再試。", ephemeral=True)


async def story_char_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    results = await asyncio.to_thread(search_story_chars, current)
    return [app_commands.Choice(name=n, value=n) for n in results]


@tree.command(name="劇情角色", description="查詢明日方舟劇情角色的簡介、出處與立繪")
@app_commands.describe(角色名稱="輸入劇情角色名稱，例如：博士、塔露拉、Ace")
@app_commands.autocomplete(角色名稱=story_char_autocomplete)
async def story_char(interaction: discord.Interaction, 角色名稱: str):
    await interaction.response.defer(thinking=True)
    try:
        data = await asyncio.to_thread(get_story_char, 角色名稱)
        if not data:
            await interaction.followup.send(
                f"❌ 找不到劇情角色「{角色名稱}」。", ephemeral=True
            )
            return

        em = discord.Embed(
            title=data["name_trad"],
            description=data["intro_trad"][:500] + ("…" if len(data["intro_trad"]) > 500 else ""),
            color=0x7B8FA1,
        )
        urls = data.get("image_urls") or []
        if urls:
            name_hans = zhconv.convert(data["name_trad"], "zh-hans")
            idx = PORTRAIT_INDEX_OVERRIDES.get(name_hans, 0)
            em.set_image(url=urls[idx] if idx < len(urls) else urls[0])
        em.set_footer(text="資料來源：PRTS Wiki・劇情角色一覽")
        await interaction.followup.send(embed=em, view=DeleteView())
    except Exception:
        await interaction.followup.send("❌ 處理時發生錯誤，請稍後再試。", ephemeral=True)


@tree.command(name="幹員資料", description="查詢明日方舟幹員基本資料")
@app_commands.describe(幹員名稱="輸入幹員名稱，例如：銀灰、能天使、推進之王")
@app_commands.autocomplete(幹員名稱=operator_autocomplete)
async def operator_info(interaction: discord.Interaction, 幹員名稱: str):
    await interaction.response.defer(thinking=True)
    try:
        data = get_operator_data(幹員名稱)

        if not data:
            await interaction.followup.send(embed=discord.Embed(
                description=f"❌ 找不到幹員「{幹員名稱}」，請確認名稱是否正確。\n繁體與簡體均可，例如：銀灰、银灰、能天使",
                color=0xFF0000,
            ))
            return

        rarity = data.get("rarity", "")
        color = RARITY_COLORS.get(rarity, 0x7289DA)
        stars = RARITY_STARS.get(rarity, rarity)

        embed = discord.Embed(
            title=f"📋 {data.get('name', 幹員名稱)}",
            description=data.get("en_name", ""),
            color=color,
            url=f"https://prts.wiki/w/{幹員名稱}",
        )

        if stars:
            embed.add_field(name="稀有度", value=stars, inline=True)
        if data.get("job_class"):
            embed.add_field(name="職業", value=data["job_class"], inline=True)
        if data.get("branch"):
            embed.add_field(name="分支", value=data["branch"], inline=_fi(data["branch"]))
        if data.get("country"):
            embed.add_field(name="所屬陣營", value=data["country"], inline=_fi(data["country"]))
        if data.get("organization"):
            embed.add_field(name="所屬組織", value=data["organization"], inline=_fi(data["organization"]))
        if data.get("tags"):
            embed.add_field(name="標籤", value=data["tags"], inline=_fi(data["tags"]))
        if data.get("trait"):
            embed.add_field(name="特性", value=data["trait"], inline=False)

        deploy = []
        if data.get("block"):
            deploy.append(f"阻擋 {data['block']}")
        if data.get("cost"):
            deploy.append(f"費用 {data['cost']}")
        if data.get("redeploy"):
            deploy.append(f"再部署 {data['redeploy']}秒")
        if data.get("atk_speed"):
            deploy.append(f"攻速 {data['atk_speed']}")
        if deploy:
            embed.add_field(name="部署數值", value=" ｜ ".join(deploy), inline=False)

        credits = []
        if data.get("artist"):
            credits.append(f"畫師：{data['artist']}")
        if data.get("jp_va"):
            credits.append(f"日文CV：{data['jp_va']}")
        if credits:
            embed.add_field(name="製作人員", value="　".join(credits), inline=False)

        images = data.get("images", [])
        if images:
            embed.set_image(url=images[0][1])
        embed.set_footer(text="資料來源：PRTS Wiki｜使用 /幹員檔案 查詢背景故事")

        embed2 = discord.Embed(
            title=f"📊 {data.get('name', 幹員名稱)}｜屬性・潛能",
            color=color,
            url=f"https://prts.wiki/w/{幹員名稱}",
        )
        for elite, label in (("0", "精零滿級"), ("1", "精一滿級"), ("2", "精二滿級")):
            if data.get(f"stats_e{elite}"):
                embed2.add_field(name=label, value=data[f"stats_e{elite}"], inline=False)
        if data.get("trust_bonus"):
            embed2.add_field(name="信賴加成", value=data["trust_bonus"], inline=False)
        range_groups: dict[str, list[str]] = {}
        for elite, label in (("0", "精零"), ("1", "精一"), ("2", "精二")):
            rid = data.get(f"range_e{elite}")
            if rid:
                range_groups.setdefault(rid, []).append(label)
        for rid, labels in range_groups.items():
            embed2.add_field(
                name=f"攻擊範圍（{'・'.join(labels)}）",
                value=render_range(rid),
                inline=True,
            )
        if data.get("potentials"):
            embed2.add_field(name="潛能提升", value=data["potentials"], inline=False)
        embed2.set_footer(text="資料來源：PRTS Wiki｜使用 /幹員檔案 查詢背景故事")

        await interaction.followup.send(embed=embed, view=OperatorView(embed, embed2, images))
    except Exception:
        await interaction.followup.send("❌ 處理時發生錯誤，請稍後再試。", ephemeral=True)


@tree.command(name="幹員檔案", description="查詢幹員基礎檔案、體檢、履歷、診斷等完整背景資料")
@app_commands.describe(幹員名稱="輸入幹員名稱，例如：銀灰、能天使")
@app_commands.autocomplete(幹員名稱=operator_autocomplete)
async def operator_lore(interaction: discord.Interaction, 幹員名稱: str):
    await interaction.response.defer(thinking=True)
    try:
        data = await asyncio.to_thread(get_lore_data, 幹員名稱)

        if not data or not data["sections"]:
            await interaction.followup.send(embed=discord.Embed(
                description=f"❌ 找不到幹員「{幹員名稱}」的檔案資料。",
                color=0xFF0000,
            ))
            return

        op = await asyncio.to_thread(get_operator_data, 幹員名稱)
        color = RARITY_COLORS.get((op or {}).get("rarity", ""), 0x7289DA)
        name = data["name"]
        url = f"https://prts.wiki/w/{zhconv.convert(幹員名稱, 'zh-hans')}"

        pages: list[tuple[str, discord.Embed]] = []
        for sec in data["sections"]:
            content = sec["content"]
            if len(content) > 4000:
                content = content[:4000] + "…（詳見 PRTS Wiki）"

            em = discord.Embed(
                title=f"📖 {name}｜{sec['title']}",
                description=content or "（暫無內容）",
                color=color,
                url=url,
            )
            cond = sec.get("condition", "")
            footer = "資料來源：PRTS Wiki"
            if cond and cond != "初始開放":
                footer += f"　🔒 {cond}"
            em.set_footer(text=footer)
            pages.append((sec["title"], em))

        await interaction.followup.send(embed=pages[0][1], view=LoreView(pages))
    except Exception:
        await interaction.followup.send("❌ 處理時發生錯誤，請稍後再試。", ephemeral=True)


@tree.command(name="幹員技能", description="查詢幹員技能、天賦與模組資訊")
@app_commands.describe(幹員名稱="輸入幹員名稱，例如：銀灰、能天使")
@app_commands.autocomplete(幹員名稱=operator_autocomplete)
async def operator_skills(interaction: discord.Interaction, 幹員名稱: str):
    await interaction.response.defer(thinking=True)
    try:
        data = await asyncio.to_thread(get_skill_data, 幹員名稱)

        if not data:
            await interaction.followup.send(embed=discord.Embed(
                description=f"❌ 找不到幹員「{幹員名稱}」，請確認名稱是否正確。",
                color=0xFF0000,
            ))
            return

        op = await asyncio.to_thread(get_operator_data, 幹員名稱)
        color = RARITY_COLORS.get((op or {}).get("rarity", ""), 0x7289DA)
        name = data["name"]
        url = f"https://prts.wiki/w/{zhconv.convert(幹員名稱, 'zh-hans')}"
        pages: list[tuple[str, discord.Embed]] = []

        # ── 技能頁 ──────────────────────────────────────────────
        for i, skill in enumerate(data["skills"], 1):
            type_line = " ｜ ".join(filter(None, [skill.get("type1"), skill.get("type2")]))
            em = discord.Embed(
                title=f"🎯 {name}｜技能 {i}：{skill['name']}",
                description=type_line or None,
                color=color,
                url=url,
            )
            is_passive = skill.get("type1") in ("被動", "被动")

            def _skill_val(desc: str, sp: str, _p: bool = is_passive) -> str:
                if sp and not _p:
                    return f"*{sp}*\n{desc}"
                return desc

            if skill.get("lv7"):
                em.add_field(name="Lv.7", value=_skill_val(skill["lv7"], skill.get("lv7_sp", "")), inline=False)
            for rank, key in [("專精 1", "m1"), ("專精 2", "m2"), ("專精 3", "m3")]:
                if skill.get(key):
                    em.add_field(name=rank, value=_skill_val(skill[key], skill.get(f"{key}_sp", "")), inline=False)
            em.set_footer(text="資料來源：PRTS Wiki")
            pages.append((f"技能 {i}", em))

        # ── 後勤技能頁 ────────────────────────────────────────────
        em = discord.Embed(title=f"🏭 {name}｜後勤技能", color=color, url=url)
        if data.get("base_skills"):
            for bs in data["base_skills"]:
                field_name = bs["name"]
                if bs.get("room"):
                    field_name = f"[{bs['room']}] {field_name}"
                if bs.get("phase"):
                    field_name += f"（{bs['phase']}開放）"
                em.add_field(name=field_name, value=bs["desc"] or "暫無描述", inline=False)
        else:
            em.description = "此幹員暫無後勤技能資料"
        em.set_footer(text="資料來源：PRTS Wiki")
        pages.append(("後勤技能", em))

        # ── 天賦頁 ──────────────────────────────────────────────
        em = discord.Embed(title=f"💫 {name}｜天賦", color=color, url=url)
        for t in data["talents"]:
            field_name = f"{t['group']}：{t['name']}" if t.get("name") else t["group"]
            cond = f"【{t['condition']}】" if t.get("condition") else ""
            field_val = f"{cond}{t['effect']}" if t.get("effect") else "暫無資料"
            em.add_field(name=field_name, value=field_val, inline=False)
        if not data["talents"]:
            em.description = "暫無天賦資料"
        em.set_footer(text="資料來源：PRTS Wiki")
        pages.append(("天賦", em))

        # ── 模組頁 ──────────────────────────────────────────────
        em = discord.Embed(title=f"🔧 {name}｜模組", color=color, url=url)
        if data["modules"]:
            for mod in data["modules"]:
                header = mod["name"] + (f"（{mod['type_code']}）" if mod.get("type_code") else "")
                if mod.get("trait"):
                    em.add_field(name=header, value=mod["trait"], inline=False)
                if mod.get("talent2"):
                    em.add_field(name="天賦更新（等級 2）", value=mod["talent2"], inline=False)
                if mod.get("talent3"):
                    em.add_field(name="天賦更新（等級 3）", value=mod["talent3"], inline=False)
        else:
            em.description = "此幹員暫無專屬模組"
        em.set_footer(text="資料來源：PRTS Wiki")
        pages.append(("模組", em))

        view = SkillView(pages, num_skills=len(data["skills"]))
        await interaction.followup.send(embed=pages[0][1], view=view)
    except Exception:
        await interaction.followup.send("❌ 處理時發生錯誤，請稍後再試。", ephemeral=True)


@tree.command(name="抽角色", description="從幹員中隨機抽取角色，可選擇老公或老婆")
@app_commands.describe(偏好="選擇老公或老婆（不填則從全部幹員中抽取）")
@app_commands.choices(偏好=[
    app_commands.Choice(name="老婆", value="老婆"),
    app_commands.Choice(name="老公", value="老公"),
])
async def draw_char(interaction: discord.Interaction, 偏好: Optional[str] = None):
    try:
        all_names = get_all_operator_names()
        if not all_names:
            await interaction.response.send_message("❌ 幹員資料尚未載入，請稍後再試。", ephemeral=True)
            return

        genders = load_operator_genders()
        if 偏好 == "老婆":
            names = [n for n in all_names if genders.get(n, "未知") in ("女", "未知")]
        elif 偏好 == "老公":
            names = [n for n in all_names if genders.get(n, "未知") in ("男", "未知")]
        else:
            names = all_names

        if not names:
            await interaction.response.send_message("❌ 篩選後無符合角色，請稍後再試。", ephemeral=True)
            return

        role_label = 偏好 if 偏好 else "角色"

        # 5% 機率抽到普瑞賽斯（限老婆或無偏好）
        if 偏好 != "老公" and random.random() < 0.05:
            await interaction.response.send_message(
                f"{interaction.user.mention} 今天的{role_label}是..."
            )
            msg = await interaction.original_response()
            spin_icons = ["🎰", "🎲", "🃏", "🎯"]
            for i in range(4):
                await asyncio.sleep(0.6)
                shown = [zhconv.convert(random.choice(names), "zh-hant") for _ in range(3)]
                await msg.edit(content=(
                    f"{interaction.user.mention} 今天的{role_label}是...\n"
                    f"> {spin_icons[i]}  ｜  **{shown[0]}**  ｜  **{shown[1]}**  ｜  **{shown[2]}**  ｜"
                ))
            await asyncio.sleep(0.6)
            await msg.edit(content=(
                f"{interaction.user.mention} 今天的{role_label}是...\n"
                f"> ✨  **命運已定！**  ✨"
            ))
            priestess_file = discord.File("priestess.png", filename="priestess.png")
            em_p = discord.Embed(
                title="普瑞賽斯",
                description=(
                    f"你抽到**我**了喔，**親愛的**～\n我就相信我們之間的連結會跨越時間與空間，"
                    f"我們將在悲傷與重逢交織的文明盡頭，再次牽起彼此的手..."
                    f"來吧，我親愛的預言家 {interaction.user.mention}"
                ),
                color=0xFF0000,
            )
            em_p.set_image(url="attachment://priestess.png")
            em_p.set_footer(text=f"今日份的{role_label}💕")
            await interaction.followup.send(embed=em_p, file=priestess_file)
            return

        name_hans = random.choice(names)
        image_task = asyncio.create_task(asyncio.to_thread(get_wife_image, name_hans))

        await interaction.response.send_message(
            f"{interaction.user.mention} 今天的{role_label}是..."
        )
        msg = await interaction.original_response()

        spin_icons = ["🎰", "🎲", "🃏", "🎯"]
        for i in range(4):
            await asyncio.sleep(0.6)
            shown = [zhconv.convert(random.choice(names), "zh-hant") for _ in range(3)]
            await msg.edit(content=(
                f"{interaction.user.mention} 今天的{role_label}是...\n"
                f"> {spin_icons[i]}  ｜  **{shown[0]}**  ｜  **{shown[1]}**  ｜  **{shown[2]}**  ｜"
            ))

        await asyncio.sleep(0.6)
        await msg.edit(content=(
            f"{interaction.user.mention} 今天的{role_label}是...\n"
            f"> ✨  **命運已定！**  ✨"
        ))

        trad_name, img_url = await image_task
        sex = genders.get(name_hans, "未知")
        em = discord.Embed(title=trad_name, color=0xFF69B4)

        if img_url:
            em.set_image(url=img_url)
        em.set_footer(text=f"今日份的{role_label}💕")
        await interaction.followup.send(embed=em)

    except Exception:
        try:
            await interaction.followup.send("❌ 處理時發生錯誤，請稍後再試。", ephemeral=True)
        except Exception:
            pass


def _gender_label(sex: str) -> str:
    """將性別值轉換為顯示標籤。未知或問號則回傳男/女。"""
    if sex == "男":
        return "男"
    if sex == "女":
        return "女"
    return "男 / 女"


def _extended_wife_result(kind: str, name_hans: str) -> tuple[str, str, str]:
    """背景執行：回傳 (繁體名稱, 圖片URL, 性別)，供擴充版抽老婆使用。"""
    if kind == "op":
        name_trad, img_url = get_wife_image(name_hans)
        sex = load_operator_genders().get(name_hans, "未知")
        return name_trad, img_url, sex
    char = get_story_char(name_hans)
    if char:
        urls = char.get("image_urls") or []
        idx = PORTRAIT_INDEX_OVERRIDES.get(name_hans, 0)
        img = urls[idx] if urls and idx < len(urls) else (urls[0] if urls else "")
        return char["name_trad"], img, char.get("gender", "未知")
    return zhconv.convert(name_hans, "zh-hant"), "", "未知"


@tree.command(name="抽角色擴充版", description="從所有幹員與劇情角色中隨機抽取角色，可選擇老公或老婆")
@app_commands.describe(偏好="選擇老公或老婆（不填則從全部角色中抽取）")
@app_commands.choices(偏好=[
    app_commands.Choice(name="老婆", value="老婆"),
    app_commands.Choice(name="老公", value="老公"),
])
async def draw_char_ex(interaction: discord.Interaction, 偏好: Optional[str] = None):
    try:
        all_op_names = get_all_operator_names()
        all_story_chars = load_story_chars()
        if not all_op_names and not all_story_chars:
            await interaction.response.send_message("❌ 資料尚未載入，請稍後再試。", ephemeral=True)
            return

        genders = load_operator_genders()

        if 偏好 == "老婆":
            op_names = [n for n in all_op_names if genders.get(n, "未知") in ("女", "未知")]
            story_chars = [c for c in all_story_chars if c.get("gender", "未知") in ("女", "未知")]
        elif 偏好 == "老公":
            op_names = [n for n in all_op_names if genders.get(n, "未知") in ("男", "未知")]
            story_chars = [c for c in all_story_chars if c.get("gender", "未知") in ("男", "未知")]
        else:
            op_names = all_op_names
            story_chars = all_story_chars

        pool = [("op", n) for n in op_names] + [("char", c["name_hans"]) for c in story_chars]
        if not pool:
            await interaction.response.send_message("❌ 篩選後無符合角色，請稍後再試。", ephemeral=True)
            return

        all_display = (
            [zhconv.convert(n, "zh-hant") for n in op_names]
            + [c["name_trad"] for c in story_chars]
        )
        role_label = 偏好 if 偏好 else "角色"

        # 5% 機率抽到普瑞賽斯（限老婆或無偏好）
        if 偏好 != "老公" and random.random() < 0.05:
            await interaction.response.send_message(
                f"{interaction.user.mention} 今天的{role_label}是..."
            )
            msg = await interaction.original_response()
            spin_icons = ["🎰", "🎲", "🃏", "🎯"]
            for i in range(4):
                await asyncio.sleep(0.6)
                shown = [random.choice(all_display) for _ in range(3)]
                await msg.edit(content=(
                    f"{interaction.user.mention} 今天的{role_label}是...\n"
                    f"> {spin_icons[i]}  ｜  **{shown[0]}**  ｜  **{shown[1]}**  ｜  **{shown[2]}**  ｜"
                ))
            await asyncio.sleep(0.6)
            await msg.edit(content=(
                f"{interaction.user.mention} 今天的{role_label}是...\n"
                f"> ✨  **命運已定！**  ✨"
            ))
            priestess_file = discord.File("priestess.png", filename="priestess.png")
            em_p = discord.Embed(
                title="普瑞賽斯",
                description=(
                    f"你抽到**我**了喔，**親愛的**～\n我就相信我們之間的連結會跨越時間與空間，"
                    f"我們將在悲傷與重逢交織的文明盡頭，再次牽起彼此的手..."
                    f"來吧，我親愛的預言家 {interaction.user.mention}"
                ),
                color=0xFF0000,
            )
            em_p.set_image(url="attachment://priestess.png")
            em_p.set_footer(text=f"今日份的{role_label}💕")
            await interaction.followup.send(embed=em_p, file=priestess_file)
            return

        kind, name_hans = random.choice(pool)
        image_task = asyncio.create_task(asyncio.to_thread(_extended_wife_result, kind, name_hans))

        await interaction.response.send_message(
            f"{interaction.user.mention} 今天的{role_label}是..."
        )
        msg = await interaction.original_response()

        spin_icons = ["🎰", "🎲", "🃏", "🎯"]
        for i in range(4):
            await asyncio.sleep(0.6)
            shown = [random.choice(all_display) for _ in range(3)]
            await msg.edit(content=(
                f"{interaction.user.mention} 今天的{role_label}是...\n"
                f"> {spin_icons[i]}  ｜  **{shown[0]}**  ｜  **{shown[1]}**  ｜  **{shown[2]}**  ｜"
            ))

        await asyncio.sleep(0.6)
        await msg.edit(content=(
            f"{interaction.user.mention} 今天的{role_label}是...\n"
            f"> ✨  **命運已定！**  ✨"
        ))

        trad_name, img_url, sex = await image_task
        em = discord.Embed(title=trad_name, color=0xFF69B4)

        if img_url:
            em.set_image(url=img_url)
        em.set_footer(text=f"今日份的{role_label}💕")
        await interaction.followup.send(embed=em)

    except Exception:
        try:
            await interaction.followup.send("❌ 處理時發生錯誤，請稍後再試。", ephemeral=True)
        except Exception:
            pass


@tree.command(name="陸服卡池未來視", description="顯示明日方舟陸服限時尋訪一覽（由新至舊）")
async def gacha_future(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        pools = await asyncio.to_thread(get_gacha_pools)
        if not pools:
            await interaction.followup.send(embed=discord.Embed(
                description="❌ 無法取得尋訪資料，請稍後再試。",
                color=0xFF0000,
            ))
            return

        PER_PAGE = 6

        def fmt_ops(ops: list[str], max_show: int = 12) -> str:
            if not ops:
                return ""
            if len(ops) > max_show:
                return "、".join(ops[:max_show]) + f"…等{len(ops)}位"
            return "、".join(ops)

        def make_embed(page_pools: list[dict], page: int, total_pages: int) -> discord.Embed:
            em = discord.Embed(
                title="📅 陸服限時尋訪一覽",
                color=0xE8B84B,
                url="https://prts.wiki/w/卡池一览",
            )
            for p in page_pools:
                lines = [f"🕐 開啟：{p['start_time']}"]
                if p["ops_6"] and p["ops_other"]:
                    lines.append(f"6★：{fmt_ops(p['ops_6'])}")
                    lines.append(f"5★/4★：{fmt_ops(p['ops_other'])}")
                elif p["ops_6"]:
                    lines.append(f"特定幹員：{fmt_ops(p['ops_6'])}")
                elif p["ops_other"]:
                    lines.append(f"特定幹員：{fmt_ops(p['ops_other'])}")
                em.add_field(name=p["name"], value="\n".join(lines), inline=False)
            em.set_footer(text=f"第 {page}/{total_pages} 頁　資料來源：PRTS Wiki")
            return em

        total_pages = (len(pools) + PER_PAGE - 1) // PER_PAGE
        pages = [
            (f"第{i+1}頁", make_embed(pools[i*PER_PAGE:(i+1)*PER_PAGE], i+1, total_pages))
            for i in range(total_pages)
        ]

        await interaction.followup.send(embed=pages[0][1], view=MaterialView(pages))
    except Exception:
        await interaction.followup.send("❌ 處理時發生錯誤，請稍後再試。", ephemeral=True)


@tree.command(name="幹員時裝", description="查詢幹員的時裝圖片、品牌、畫師與取得方式")
@app_commands.describe(幹員名稱="輸入幹員名稱，例如：銀灰、能天使")
@app_commands.autocomplete(幹員名稱=operator_autocomplete)
async def operator_skins(interaction: discord.Interaction, 幹員名稱: str):
    await interaction.response.defer(thinking=True)
    try:
        data = await asyncio.to_thread(get_skin_data, 幹員名稱)

        if not data:
            await interaction.followup.send(embed=discord.Embed(
                description=f"❌ 找不到幹員「{幹員名稱}」，請確認名稱是否正確。",
                color=0xFF0000,
            ))
            return

        if not data["skins"]:
            await interaction.followup.send(embed=discord.Embed(
                title=f"👘 {data['name']}",
                description="該幹員尚未擁有時裝。",
                color=0x7289DA,
            ))
            return

        op = await asyncio.to_thread(get_operator_data, 幹員名稱)
        color = RARITY_COLORS.get((op or {}).get("rarity", ""), 0x7289DA)
        name = data["name"]
        url = f"https://prts.wiki/w/{zhconv.convert(幹員名稱, 'zh-hans')}"
        total = len(data["skins"])

        embeds: list[discord.Embed] = []
        for i, skin in enumerate(data["skins"], 1):
            em = discord.Embed(
                title=f"👘 {name}｜{skin['name']}",
                color=color,
                url=url,
            )
            em.add_field(name="品牌", value=skin["series"] or "—", inline=True)
            em.add_field(name="畫師", value=skin["artist"] or "—", inline=True)
            em.add_field(name="價格", value=skin["price"] or "—", inline=True)
            if skin["image_url"]:
                em.set_image(url=skin["image_url"])
            em.set_footer(text=f"時裝 {i}/{total}　資料來源：PRTS Wiki")
            embeds.append(em)

        await interaction.followup.send(embed=embeds[0], view=SkinView(embeds))
    except Exception:
        await interaction.followup.send("❌ 處理時發生錯誤，請稍後再試。", ephemeral=True)


@tree.command(name="幹員素材計算", description="查詢技能專精與模組解鎖所需的素材")
@app_commands.describe(幹員名稱="輸入幹員名稱，例如：銀灰、能天使")
@app_commands.autocomplete(幹員名稱=operator_autocomplete)
async def operator_materials(interaction: discord.Interaction, 幹員名稱: str):
    await interaction.response.defer(thinking=True)
    try:
        data = await asyncio.to_thread(get_material_data, 幹員名稱)

        if not data:
            await interaction.followup.send(embed=discord.Embed(
                description=f"❌ 找不到幹員「{幹員名稱}」，請確認名稱是否正確。",
                color=0xFF0000,
            ))
            return

        op = await asyncio.to_thread(get_operator_data, 幹員名稱)
        color = RARITY_COLORS.get((op or {}).get("rarity", ""), 0x7289DA)
        name = data["name"]
        url = f"https://prts.wiki/w/{zhconv.convert(幹員名稱, 'zh-hans')}"
        pages: list[tuple[str, discord.Embed]] = []

        # ── 技能專精素材頁 ──────────────────────────────────────────
        em = discord.Embed(title=f"📦 {name}｜技能專精素材", color=color, url=url)
        if data["masteries"]:
            for i, s in enumerate(data["masteries"], 1):
                lines = []
                for rank, key in [("專精1", "m1"), ("專精2", "m2"), ("專精3", "m3")]:
                    if s.get(key):
                        lines.append(f"**{rank}**：{_fmt_mat(s[key])}")
                if lines:
                    em.add_field(
                        name=f"技能{i}：{s['name']}",
                        value="\n".join(lines),
                        inline=False,
                    )
        else:
            em.description = "此幹員無技能專精資料"
        em.set_footer(text="資料來源：PRTS Wiki")
        pages.append(("技能專精", em))

        # ── 模組解鎖素材頁 ──────────────────────────────────────────
        em = discord.Embed(title=f"📦 {name}｜模組解鎖素材", color=color, url=url)
        if data["mod_materials"]:
            for mod in data["mod_materials"]:
                header = mod["name"]
                if mod.get("type_code"):
                    header += f"（{mod['type_code']}）"
                cond_parts = []
                if mod.get("unlock_level"):
                    cond_parts.append(f"Lv.{mod['unlock_level']}")
                if mod.get("unlock_trust"):
                    cond_parts.append(f"信賴 {mod['unlock_trust']}%")
                cond = "　解鎖：" + "、".join(cond_parts) if cond_parts else ""
                lines = [cond] if cond else []
                for lv, key in [("等級1", "cost1"), ("等級2", "cost2"), ("等級3", "cost3")]:
                    if mod.get(key):
                        lines.append(f"**{lv}**：{_fmt_mat(mod[key])}")
                em.add_field(name=header, value="\n".join(lines) or "暫無資料", inline=False)
        else:
            em.description = "此幹員暫無專屬模組"
        em.set_footer(text="資料來源：PRTS Wiki")
        pages.append(("模組解鎖", em))

        await interaction.followup.send(embed=pages[0][1], view=MaterialView(pages))
    except Exception:
        await interaction.followup.send("❌ 處理時發生錯誤，請稍後再試。", ephemeral=True)


# ── 語音猜角色 ────────────────────────────────────────────────────────────────

# (user_id, mode_key) → 數值；mode_key: "random" | "title"
_voice_streaks: dict[tuple[int, str], int] = {}
_voice_bests: dict[tuple[int, str], int] = {}

# 全球排名持久化：{mode_key: {uid_str: [score, display_name]}}
_RECORDS_FILE = "voice_records.json"
_global_records: dict[str, dict[str, list]] = {"random": {}, "title": {}, "tap": {}}


def _load_voice_records() -> None:
    if not os.path.exists(_RECORDS_FILE):
        return
    try:
        with open(_RECORDS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for mk in ("random", "title", "tap"):
            for uid_str, val in data.get(mk, {}).items():
                if isinstance(val, list) and len(val) == 2:
                    _global_records[mk][uid_str] = val
    except Exception:
        pass


def _save_voice_records() -> None:
    try:
        with open(_RECORDS_FILE, "w", encoding="utf-8") as f:
            json.dump(_global_records, f, ensure_ascii=False)
    except Exception:
        pass


def _update_global_record(uid: int, display_name: str, mk: str, score: int) -> None:
    uid_str = str(uid)
    if score > _global_records[mk].get(uid_str, [0])[0]:
        _global_records[mk][uid_str] = [score, display_name]
        _save_voice_records()


def _get_rank_info(uid: int, mk: str) -> tuple[int, int, int, str]:
    """(global_best_score, user_rank, total_players, global_best_holder_name)"""
    records = _global_records[mk]
    uid_str = str(uid)
    if not records:
        return 0, 1, 1, ""
    sorted_scores = sorted((v[0] for v in records.values()), reverse=True)
    global_best = sorted_scores[0]
    holder = max(records.items(), key=lambda kv: kv[1][0])
    global_holder_name = holder[1][1]
    user_score = records.get(uid_str, [0])[0]
    rank = sum(1 for s in sorted_scores if s > user_score) + 1
    return global_best, rank, len(records), global_holder_name


def _mode_key(mode: str) -> str:
    if mode == "title":
        return "title"
    if mode == "tap":
        return "tap"
    return "random"


def _mode_tag(mode: str) -> str:
    if mode == "title":
        return "♟️ Arknights模式"
    if mode == "tap":
        return "👆 觸摸模式"
    return "🎲 全語音模式"


def _mode_fetch(mode: str):
    if mode == "title":
        return get_wikig_title_voice
    if mode == "tap":
        return get_wikig_tap_voice
    return get_wikig_random_voice


class VoiceGuessButton(discord.ui.Button):
    def __init__(self, label: str, choice: str, parent_view: "VoiceGuessView"):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.choice = choice
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        view = self.parent_view
        if view.answered:
            await interaction.response.defer()
            return
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("❌ 這不是你的遊戲！", ephemeral=True)
            return

        view.answered = True
        view.stop()

        for item in view.children:
            item.disabled = True  # type: ignore
            if isinstance(item, VoiceGuessButton):
                if item.choice == view.correct:
                    item.style = discord.ButtonStyle.success
                elif item.choice == self.choice:
                    item.style = discord.ButtonStyle.danger

        uid = view.user_id
        mk = _mode_key(view.mode)
        tag = _mode_tag(view.mode)
        is_correct = self.choice == view.correct

        if is_correct:
            new_streak = _voice_streaks.get((uid, mk), 0) + 1
            _voice_streaks[(uid, mk)] = new_streak
            if new_streak > _voice_bests.get((uid, mk), 0):
                _voice_bests[(uid, mk)] = new_streak
            embed = discord.Embed(
                title="✅ 答對了！",
                description=f"是 **{view.correct}**！\n🔥 連答：{new_streak} 題　｜　{tag}",
                color=0x2ECC71,
            )
            await interaction.response.edit_message(embed=embed, view=view)
            await asyncio.sleep(1.5)
            await interaction.delete_original_response()
            await _send_voice_guess(interaction, followup=True, mode=view.mode)
        else:
            current = _voice_streaks.get((uid, mk), 0)
            _voice_streaks[(uid, mk)] = 0
            best = _voice_bests.get((uid, mk), 0)

            _update_global_record(uid, interaction.user.display_name, mk, best)
            global_best, rank, total, holder = _get_rank_info(uid, mk)

            holder_text = f"（{holder}）" if holder else ""
            footer = (
                f"{tag} 全球最高：{global_best} 題{holder_text}"
                f"　｜　你的名次：第 {rank} 名 / {total} 人"
            )
            embed = discord.Embed(
                title="❌ 答錯了！",
                description=(
                    f"正確答案是 **{view.correct}**\n"
                    f"本次連答：**{current}** 題　｜　{tag} 歷史最高：**{best}** 題"
                ),
                color=0xE74C3C,
            )
            embed.set_footer(text=footer)
            await interaction.response.edit_message(embed=embed, view=view)


class VoiceGuessView(discord.ui.View):
    def __init__(self, correct: str, choices: list[str], user_id: int, mode: str = "random"):
        super().__init__(timeout=60)
        self.correct = correct
        self.user_id = user_id
        self.answered = False
        self.mode = mode
        for i, ch in enumerate(choices):
            self.add_item(VoiceGuessButton(
                label=f"{chr(65 + i)}. {ch}",
                choice=ch,
                parent_view=self,
            ))

    async def on_timeout(self):
        self.answered = True
        for item in self.children:
            item.disabled = True  # type: ignore


async def _send_voice_guess(
    interaction: discord.Interaction,
    followup: bool = False,
    mode: str = "random",
):
    """選出幹員、下載語音、發送題目。mode: 'random' | 'title' | 'tap'"""
    ops = await asyncio.to_thread(load_wikig_operators)
    if len(ops) < 4:
        await interaction.followup.send("❌ 無法載入幹員清單，請稍後再試。", ephemeral=True)
        return

    cn_map = await asyncio.to_thread(load_wikig_cn_names)
    fetch_voice = _mode_fetch(mode)

    voice_data: bytes | None = None
    correct_en: str = ""
    pool_en: list[str] = []

    for _ in range(8):
        pool = random.sample(ops, 4)
        candidate = pool[0]
        data = await asyncio.to_thread(fetch_voice, candidate)
        if data:
            voice_data = data
            correct_en = candidate
            random.shuffle(pool)
            pool_en = pool
            break

    if not voice_data:
        await interaction.followup.send("❌ 無法取得語音檔案，請稍後再試。", ephemeral=True)
        return

    def display(en: str) -> str:
        key = en.lower()
        return cn_map.get(key) or cn_map.get(key.replace(" ", "")) or en

    correct_display = display(correct_en)
    choices_display = [display(en) for en in pool_en]

    uid = interaction.user.id
    mk = _mode_key(mode)
    streak = _voice_streaks.get((uid, mk), 0)
    tag = _mode_tag(mode)
    embed = discord.Embed(
        title="🎙️ 猜猜這是哪位幹員的語音？",
        description=f"{tag}　｜　🔥 目前連答：{streak} 題",
        color=0x4169E1,
    )
    file = discord.File(io.BytesIO(voice_data), filename="voice.ogg")
    view = VoiceGuessView(
        correct=correct_display,
        choices=choices_display,
        user_id=uid,
        mode=mode,
    )

    await interaction.followup.send(embed=embed, file=file, view=view)


@tree.command(name="語音猜角色", description="聆聽幹員語音（JP），猜猜是誰！答對繼續出題，答錯結束並公布答案")
@app_commands.describe(模式="選擇語音範圍（預設：全語音）")
@app_commands.choices(模式=[
    app_commands.Choice(name="全語音", value="random"),
    app_commands.Choice(name="Arknights模式", value="title"),
    app_commands.Choice(name="觸摸模式", value="tap"),
])
async def voice_guess_cmd(interaction: discord.Interaction, 模式: Optional[str] = None):
    try:
        await interaction.response.defer()
    except discord.errors.NotFound:
        return
    await _send_voice_guess(interaction, followup=True, mode=模式 or "random")


async def _sync_and_announce():
    await tree.sync()
    print("📡 斜線指令已同步")


@client.event
async def on_ready():
    print(f"✅ Bot 已上線：{client.user}（ID: {client.user.id}）")
    _load_voice_records()
    asyncio.create_task(_sync_and_announce())
    asyncio.create_task(asyncio.to_thread(load_operator_names))
    asyncio.create_task(asyncio.to_thread(load_range_data))
    asyncio.create_task(asyncio.to_thread(load_real_names))
    asyncio.create_task(asyncio.to_thread(load_story_chars))
    asyncio.create_task(asyncio.to_thread(load_drive_images))
    asyncio.create_task(asyncio.to_thread(load_operator_genders))
    asyncio.create_task(asyncio.to_thread(load_wikig_operators))
    asyncio.create_task(asyncio.to_thread(load_wikig_cn_names))
    print("⏳ 正在背景載入資料...")


client.run(TOKEN)
