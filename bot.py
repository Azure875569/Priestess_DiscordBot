import asyncio
import os
import discord
import zhconv
from discord import app_commands
from dotenv import load_dotenv
from scraper import get_operator_data, get_skill_data, load_operator_names, load_range_data, render_range, search_operator_names, RARITY_STARS

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


class SkillView(discord.ui.View):
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

    data = get_operator_data(幹員名稱)

    if not data:
        embed = discord.Embed(
            description=f"❌ 找不到幹員「{幹員名稱}」，請確認名稱是否正確。\n繁體與簡體均可，例如：銀灰、银灰、能天使",
            color=0xFF0000,
        )
        await interaction.followup.send(embed=embed)
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

    # 基本資訊
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

    # 基礎數值（部署相關）
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

    # 製作人員
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

    # 建立第二頁（屬性・潛能）
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
    # 攻擊範圍（依 range ID 分組，相同則合併標籤）
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


@tree.command(name="幹員檔案", description="查詢幹員背景故事（檔案一～四）")
@app_commands.describe(幹員名稱="輸入幹員名稱，例如：銀灰、能天使")
@app_commands.autocomplete(幹員名稱=operator_autocomplete)
async def operator_lore(interaction: discord.Interaction, 幹員名稱: str):
    await interaction.response.defer(thinking=True)

    data = get_operator_data(幹員名稱)

    if not data:
        embed = discord.Embed(
            description=f"❌ 找不到幹員「{幹員名稱}」的資料。",
            color=0xFF0000,
        )
        await interaction.followup.send(embed=embed)
        return

    has_lore = any(data.get(f"file{i}") for i in range(1, 5))
    if not has_lore:
        await interaction.followup.send(f"「{data.get('name', 幹員名稱)}」目前沒有檔案資料。")
        return

    embed = discord.Embed(
        title=f"📖 {data.get('name', 幹員名稱)}｜幹員檔案",
        color=RARITY_COLORS.get(data.get("rarity", ""), 0x7289DA),
        url=f"https://prts.wiki/w/{幹員名稱}",
    )

    for i in range(1, 5):
        content = data.get(f"file{i}", "")
        if content:
            # Discord embed field value 限制 1024 字元
            if len(content) > 1000:
                content = content[:1000] + "…（詳見 PRTS Wiki）"
            embed.add_field(name=f"檔案{i}", value=content, inline=False)

    embed.set_footer(text="資料來源：PRTS Wiki")
    await interaction.followup.send(embed=embed, view=DeleteView())


@tree.command(name="幹員技能", description="查詢幹員技能、天賦與模組資訊")
@app_commands.describe(幹員名稱="輸入幹員名稱，例如：銀灰、能天使")
@app_commands.autocomplete(幹員名稱=operator_autocomplete)
async def operator_skills(interaction: discord.Interaction, 幹員名稱: str):
    await interaction.response.defer(thinking=True)

    data = await asyncio.to_thread(get_skill_data, 幹員名稱)

    if not data:
        embed = discord.Embed(
            description=f"❌ 找不到幹員「{幹員名稱}」，請確認名稱是否正確。",
            color=0xFF0000,
        )
        await interaction.followup.send(embed=embed)
        return

    # 取稀有度顏色
    op = await asyncio.to_thread(get_operator_data, 幹員名稱)
    color = RARITY_COLORS.get((op or {}).get("rarity", ""), 0x7289DA)
    name = data["name"]
    url = f"https://prts.wiki/w/{zhconv.convert(幹員名稱, 'zh-hans')}"
    pages: list[tuple[str, discord.Embed]] = []

    # ── 技能頁 ────────────────────────────────────────────────
    for i, skill in enumerate(data["skills"], 1):
        type_line = " ｜ ".join(filter(None, [skill.get("type1"), skill.get("type2")]))
        em = discord.Embed(
            title=f"🎯 {name}｜技能 {i}：{skill['name']}",
            description=type_line or None,
            color=color,
            url=url,
        )
        is_passive = skill.get("type1") in ("被動", "被动")

        def _skill_val(desc: str, sp: str) -> str:
            if sp and not is_passive:
                return f"*{sp}*\n{desc}"
            return desc

        if skill.get("lv7"):
            em.add_field(name="Lv.7", value=_skill_val(skill["lv7"], skill.get("lv7_sp", "")), inline=False)
        for rank, key in [("專精 1", "m1"), ("專精 2", "m2"), ("專精 3", "m3")]:
            if skill.get(key):
                em.add_field(name=rank, value=_skill_val(skill[key], skill.get(f"{key}_sp", "")), inline=False)
        em.set_footer(text="資料來源：PRTS Wiki")
        pages.append((f"技能 {i}", em))

    # ── 後勤技能頁 ──────────────────────────────────────────────
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

    # ── 天賦頁 ────────────────────────────────────────────────
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

    # ── 模組頁 ────────────────────────────────────────────────
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

    view = SkillView(pages)
    await interaction.followup.send(embed=pages[0][1], view=view)


@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot 已上線：{client.user}（ID: {client.user.id}）")
    print("📡 斜線指令已同步，首次使用可能需要幾分鐘生效")
    asyncio.create_task(asyncio.to_thread(load_operator_names))
    asyncio.create_task(asyncio.to_thread(load_range_data))
    print("⏳ 正在背景載入幹員清單與範圍資料...")


client.run(TOKEN)
