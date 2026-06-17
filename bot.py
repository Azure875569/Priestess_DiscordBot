import asyncio
import os
import discord
import zhconv
from discord import app_commands
from dotenv import load_dotenv
from scraper import get_operator_data, get_skill_data, get_material_data, get_lore_data, load_operator_names, load_range_data, render_range, search_operator_names, RARITY_STARS

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
    if not current:
        return []
    results = await asyncio.to_thread(search_operator_names, current)
    return [
        app_commands.Choice(name=zhconv.convert(name, "zh-hant"), value=name)
        for name in results
    ]


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


@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot 已上線：{client.user}（ID: {client.user.id}）")
    print("📡 斜線指令已同步，首次使用可能需要幾分鐘生效")
    asyncio.create_task(asyncio.to_thread(load_operator_names))
    asyncio.create_task(asyncio.to_thread(load_range_data))
    print("⏳ 正在背景載入幹員清單與範圍資料...")


client.run(TOKEN)
