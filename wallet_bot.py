import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import asyncio
import json
import os
from datetime import datetime

# ==================== CONFIGURATION ====================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your bot token
GUILD_ID = 1468429630619783229 # Replace with your server ID
ADMIN_ROLE_ID =  1416377703430623283 # Replace with admin role ID
STAFF_ROLE_ID = 1468517267926028392  # Replace with staff role ID

# Currency symbol (M = Million, OSRS style)
CURRENCY_SYMBOL = "M"
CURRENCY_EMOJI = "💰"

# ==================== DATA STORAGE ====================
DATA_FILE = "bot_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "wallets": {},
        "orders": {},
        "staff": [],
        "applications": {},
        "feedback": []
    }

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

data = load_data()

# ==================== BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class OSRSBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):

        self.add_view(ApplicationView())  # <-- YAHAN

        await self.tree.sync()
        print(f"Bot logged in as {self.user}")

bot = OSRSBot()

# ==================== EMBED STYLES ====================
def create_embed(title, description=None, color=0x5865F2):
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now()
    )
    embed.set_footer(text="Powered by perez")
    return embed

def format_money(amount):
    """Format amount with M suffix"""
    return f"{amount}{CURRENCY_SYMBOL}"

# ==================== WALLET SYSTEM ====================
class WalletSystem:
    @staticmethod
    def get_wallet(user_id):
        user_id = str(user_id)
        if user_id not in data["wallets"]:
            data["wallets"][user_id] = {
                "balance": 0,
                "deposited": 0,
                "completed_jobs": 0,
                "total_earnings": 0,
                "rank": 0
            }
            save_data(data)
        return data["wallets"][user_id]
    
    @staticmethod
    def add_balance(user_id, amount):
        wallet = WalletSystem.get_wallet(user_id)
        wallet["balance"] += amount
        save_data(data)
        return wallet
    
    @staticmethod
    def remove_balance(user_id, amount):
        wallet = WalletSystem.get_wallet(user_id)
        if wallet["balance"] >= amount:
            wallet["balance"] -= amount
            save_data(data)
            return True, wallet
        return False, wallet
    
    @staticmethod
    def add_deposit(user_id, amount):
        wallet = WalletSystem.get_wallet(user_id)
        wallet["deposited"] += amount
        save_data(data)
        return wallet

# ==================== ORDER SYSTEM ====================
class OrderSystem:
    order_counter = len(data["orders"]) + 1
    
    @staticmethod
    def create_order(customer_id, description, total_value, worker_take, deposit=0):
        order_id = OrderSystem.order_counter
        OrderSystem.order_counter += 1
        
        data["orders"][str(order_id)] = {
            "id": order_id,
            "customer": str(customer_id),
            "worker": None,
            "description": description,
            "total_value": total_value,
            "worker_take": worker_take,
            "deposit": deposit,
            "status": "pending",  # pending, accepted, completed
            "created_at": datetime.now().isoformat()
        }
        save_data(data)
        return order_id
    
    @staticmethod
    def claim_order(order_id, worker_id):
        order = data["orders"].get(str(order_id))
        if order and order["status"] == "pending":
            order["worker"] = str(worker_id)
            order["status"] = "accepted"
            save_data(data)
            return True
        return False
    
    @staticmethod
    def complete_order(order_id):
        order = data["orders"].get(str(order_id))
        if order and order["status"] == "accepted":
            order["status"] = "completed"
            # Update worker stats
            worker_id = order["worker"]
            wallet = WalletSystem.get_wallet(worker_id)
            wallet["completed_jobs"] += 1
            wallet["total_earnings"] += order["worker_take"]
            save_data(data)
            return True
        return False

# ==================== VIEWS & BUTTONS ====================
class ClaimOrderView(View):
    def __init__(self, order_id):
        super().__init__(timeout=None)
        self.order_id = order_id

    @discord.ui.button(
        label="Claim Order",
        style=discord.ButtonStyle.blurple,
        emoji="📝",
        custom_id="claim_order_button"
    )
    async def claim_button(
        self,
        interaction: discord.Interaction,
        button: Button
    ):

        order = data["orders"].get(str(self.order_id))

        if not order:
            return await interaction.response.send_message(
                "Order not found!",
                ephemeral=True
            )

        if order["status"] != "pending":
            return await interaction.response.send_message(
                "This order has already been claimed!",
                ephemeral=True
            )

        # CHECK STAFF ROLE
        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)

        if staff_role not in interaction.user.roles:
            return await interaction.response.send_message(
                "Only staff can claim orders!",
                ephemeral=True
            )

        # CLAIM ORDER
        success = OrderSystem.claim_order(
            self.order_id,
            interaction.user.id
        )

        if success:

            customer = interaction.guild.get_member(
                int(order["customer"])
            )

            worker = interaction.user

            # =========================
            # CREATE TICKET CHANNEL
            # =========================
            overwrites = {
                interaction.guild.default_role:
                    discord.PermissionOverwrite(
                        view_channel=False
                    ),

                customer:
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    ),

                worker:
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )
            }

            ticket_channel = await interaction.guild.create_text_channel(
                name=f"order-{self.order_id}",
                overwrites=overwrites
            )

            # =========================
            # TICKET EMBED
            # =========================
            embed = create_embed(
                "✅ Order Accepted",
                f"<@{order['customer']}>, your order has been accepted by {interaction.user.mention}",
                0x00FF00
            )

            embed.add_field(
                name="Order ID",
                value=f"#{self.order_id}",
                inline=True
            )

            embed.add_field(
                name="Total Value",
                value=format_money(order['total_value']),
                inline=True
            )

            embed.add_field(
                name="Worker",
                value=interaction.user.mention,
                inline=True
            )

            embed.add_field(
                name="Deposit",
                value=format_money(order['deposit']),
                inline=True
            )

            embed.add_field(
                name="Description",
                value=order['description'],
                inline=False
            )

            embed.add_field(
                name="Account Details",
                value="Write your account details via https://privnote.com/\n\nDo not open the link after creating it.",
                inline=False
            )

            # SEND EMBED IN TICKET
            await ticket_channel.send(
                content=f"{customer.mention} {worker.mention}",
                embed=embed
            )

            # =========================
            # REMOVE ORIGINAL ORDER EMBED
            # =========================
            claimed_embed = create_embed(
                "✅ Order Claimed",
                f"Order #{self.order_id} has been claimed by {worker.mention}",
                0x00FF00
            )

            await interaction.message.edit(
                embed=claimed_embed,
                view=None
            )

            await interaction.response.send_message(
                f"Ticket created: {ticket_channel.mention}",
                ephemeral=True
            )

class FeedbackView(View):
    def __init__(self, order_id):
        super().__init__(timeout=None)
        self.order_id = order_id
    
    @discord.ui.button(label="Feedback", style=discord.ButtonStyle.green, emoji="📝")
    async def feedback_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(FeedbackModal(self.order_id))
    
    @discord.ui.button(label="Anonymous Feedback", style=discord.ButtonStyle.gray, emoji="🕵️")
    async def anon_feedback_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(FeedbackModal(self.order_id, anonymous=True))

class FeedbackModal(Modal, title="Order Feedback"):
    rating = TextInput(label="Rating (1-5)", placeholder="Enter 1-5", max_length=1)
    comment = TextInput(label="Comment", style=discord.TextStyle.paragraph, placeholder="Your feedback...", required=False)
    
    def __init__(self, order_id, anonymous=False):
        super().__init__()
        self.order_id = order_id
        self.anonymous = anonymous
    
    async def on_submit(self, interaction: discord.Interaction):
        rating = self.rating.value
        comment = self.comment.value or "No comment"
        
        data["feedback"].append({
            "order_id": self.order_id,
            "user": str(interaction.user.id) if not self.anonymous else "Anonymous",
            "rating": rating,
            "comment": comment,
            "date": datetime.now().isoformat()
        })
        save_data(data)
        
        # Add bonus to wallet
        wallet = WalletSystem.get_wallet(interaction.user.id)
        wallet["balance"] += 10  # 10M bonus for feedback
        save_data(data)
        
        await interaction.response.send_message(
            f"Thank you for your feedback! {CURRENCY_EMOJI} 10M has been added to your wallet!",
            ephemeral=True
        )

class ApplicationView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Become a Worker!",
        style=discord.ButtonStyle.green,
        emoji="🏆",
        custom_id="apply_worker_button"
    )
    async def apply_button(self, interaction: discord.Interaction, button: Button):

        overwrites = {
            interaction.guild.default_role:
                discord.PermissionOverwrite(view_channel=False),

            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
        }

        # Create application ticket
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"application-{interaction.user.name}",
            overwrites=overwrites
        )

        embed = create_embed(
            "📝 Worker Application",
            f"{interaction.user.mention} please answer the questions below.",
            0xFFD700
        )

        embed.add_field(
            name="Questions",
            value=(
                "**1. Your OSRS Experience**\n"
                "**2. Daily Availability**\n"
                "**3. Why should we hire you?**\n"
                "**4. Where do you live and what is your timezone?**\n"
                "**5. Why do you want to work as a service provider?**\n"
                "**6. Rate your communication skills (1/10):**\n"
                "**7. Rate your English language (1/10):**\n"
                "**8. Do you still actively play the game?**\n"
                "**9. Your age?**\n"
                "**10. Do you have a VPN?**\n"
                "**11. Are you able to use Parsec?**\n"
                "**12. How did you find our server? Did someone vouch us to you? Who?**\n"
                "**13. Do you have your deposit ready? (Deposit is mandatory 170$)**\n"
                "**14. Your Sythe profile (link):**\n"
                "**15. Post a photo of your National ID + Take a selfie with our Discord in the background.**"
            ),
            inline=False
        )

        await ticket_channel.send(
            content=interaction.user.mention,
            embed=embed
        )

        await interaction.response.send_message(
            f"✅ Your application ticket has been created: {ticket_channel.mention}",
            ephemeral=True
        )

# ==================== SLASH COMMANDS ====================
@bot.tree.command(name="wallet", description="Check your wallet balance")
async def wallet(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    wallet_data = WalletSystem.get_wallet(target.id)
    
    embed = create_embed(
        f"{target.display_name}'s Wallet",
        f"{CURRENCY_EMOJI} Wallet",
        0x00FF00
    )
    embed.add_field(name="Balance", value=format_money(wallet_data['balance']), inline=False)
    embed.add_field(name="🏦 Deposit", value=format_money(wallet_data['deposited']), inline=True)
    embed.add_field(name="⚒️ Completed Jobs", value=str(wallet_data['completed_jobs']), inline=True)
    embed.add_field(name="👑 Total Earnings", value=format_money(wallet_data['total_earnings']), inline=True)
    
    if target.avatar:
        embed.set_thumbnail(url=target.avatar.url)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="wallet-add-balance", description="Add balance to a user (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def add_balance(interaction: discord.Interaction, user: discord.Member, amount: float):
    wallet = WalletSystem.add_balance(user.id, amount)
    
    embed = create_embed(
        "💰 Balance Added",
        f"Added {format_money(amount)} to {user.mention}'s wallet",
        0x00FF00
    )
    embed.add_field(name="New Balance", value=format_money(wallet['balance']))
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="wallet-remove-balance", description="Remove balance from a user (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def remove_balance(interaction: discord.Interaction, user: discord.Member, amount: float):
    success, wallet = WalletSystem.remove_balance(user.id, amount)
    
    if success:
        embed = create_embed(
            "💰 Balance Removed",
            f"Removed {format_money(amount)} from {user.mention}'s wallet",
            0xFF0000
        )
        embed.add_field(name="New Balance", value=format_money(wallet['balance']))
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Insufficient balance!", ephemeral=True)

@bot.tree.command(name="wallet-check-of-user", description="Check any user's wallet (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def check_wallet(interaction: discord.Interaction, user: discord.Member):
    wallet_data = WalletSystem.get_wallet(user.id)
    
    embed = create_embed(
        f"{user.display_name}'s Wallet",
        f"{CURRENCY_EMOJI} Wallet",
        0x00FF00
    )
    embed.add_field(name="Balance", value=format_money(wallet_data['balance']), inline=False)
    embed.add_field(name="🏦 Deposit", value=format_money(wallet_data['deposited']), inline=True)
    embed.add_field(name="⚒️ Completed Jobs", value=str(wallet_data['completed_jobs']), inline=True)
    embed.add_field(name="👑 Total Earnings", value=format_money(wallet_data['total_earnings']), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="order-create", description="Create a new service order(Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def create_order(
    interaction: discord.Interaction,
    description: str,
    total_value: float,
    worker_take: float,
    deposit: float = 0.0
):
    order_id = OrderSystem.create_order(
        interaction.user.id,
        description,
        total_value,
        worker_take,
        deposit
    )
    
    embed = create_embed(
        "🆕 New Order",
        f"<@{interaction.user.id}>, Please make sure to keep Customer updated as much as you can.",
        0x5865F2
    )
    embed.add_field(name="Order ID", value=f"#{order_id}", inline=True)
    embed.add_field(name="Total Value", value=format_money(total_value), inline=True)
    embed.add_field(name="Worker Take", value=format_money(worker_take), inline=True)
    embed.add_field(name="Customer", value=interaction.user.mention, inline=True)
    embed.add_field(name="Worker", value="N/A", inline=True)
    embed.add_field(name="Deposit", value=format_money(deposit), inline=True)
    embed.add_field(name="Description", value=description, inline=False)
    
    if interaction.user.avatar:
        embed.set_thumbnail(url=interaction.user.avatar.url)
    
    view = ClaimOrderView(order_id)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="order-addworker", description="Assign worker to order (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def add_worker(interaction: discord.Interaction, order_id: int, user: discord.Member):
    order = data["orders"].get(str(order_id))
    if not order:
        return await interaction.response.send_message("Order not found!", ephemeral=True)
    
    order["worker"] = str(user.id)
    order["status"] = "accepted"
    save_data(data)
    
    await interaction.response.send_message(f"Added {user.mention} as worker for order #{order_id}")

@bot.tree.command(name="order-complete", description="Mark order as complete(Admin only)")
async def complete_order(interaction: discord.Interaction, order_id: int):
    order = data["orders"].get(str(order_id))
    if not order:
        return await interaction.response.send_message("Order not found!", ephemeral=True)
    
    if order["worker"] != str(interaction.user.id):
        # Check if admin
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("You are not the worker for this order!", ephemeral=True)
    
    success = OrderSystem.complete_order(order_id)
    if success:
        embed = create_embed(
            "✅ Complete",
            f"Order #{order_id} is now complete.",
            0x00FF00
        )
        embed.add_field(name="Customer", value=f"<@{order['customer']}>", inline=True)
        embed.add_field(name="Order Value", value=format_money(order['total_value']), inline=True)
        embed.add_field(name="Total Spent", value=format_money(order['total_value']), inline=True)
        embed.add_field(
            name="Feedback",
            value="Please leave us a vouch at #✅-vouches and #💬-discord-feedback\n\nAfter you leave the vouchers please notify us and we will add 10m to ur wallet to use later on our services",
            inline=False
        )
        
        view = FeedbackView(order_id)
        await interaction.response.send_message(embed=embed, view=view)
    else:
        await interaction.response.send_message("Could not complete order!", ephemeral=True)

@bot.tree.command(name="complete_job_request", description="Post completed job embed")
async def complete_job_request(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    order_id: int,
    image: discord.Attachment = None
):
    order = data["orders"].get(str(order_id))
    if not order:
        return await interaction.response.send_message("Order not found!", ephemeral=True)
    
    embed = create_embed(
        "✅ Job Completed",
        f"Order #{order_id} has been completed successfully!",
        0x00FF00
    )
    embed.add_field(name="Completed By", value=interaction.user.mention, inline=True)
    embed.add_field(name="Order Value", value=format_money(order['total_value']), inline=True)
    
    if image:
        embed.set_image(url=image.url)
    
    await channel.send(embed=embed)
    await interaction.response.send_message(f"Posted completion message in {channel.mention}", ephemeral=True)

@bot.tree.command(name="tip-user", description="Tip a user")
async def tip_user(interaction: discord.Interaction, user: discord.Member, amount: float):
    if amount <= 0:
        return await interaction.response.send_message("Amount must be positive!", ephemeral=True)
    
    sender_wallet = WalletSystem.get_wallet(interaction.user.id)
    if sender_wallet['balance'] < amount:
        return await interaction.response.send_message("Insufficient balance!", ephemeral=True)
    
    WalletSystem.remove_balance(interaction.user.id, amount)
    WalletSystem.add_balance(user.id, amount)
    
    embed = create_embed(
        "💸 Tip Sent",
        f"{interaction.user.mention} tipped {user.mention}",
        0xFFD700
    )
    embed.add_field(name="Amount", value=format_money(amount))
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="calculator-skill-lv-to-lv", description="Calculate skill XP/GP from level to level")
async def calculator(interaction: discord.Interaction, skillname: str, start_level: int, finish_level: int):
    # OSRS XP table approximation
    def xp_for_level(level):
        total = 0
        for i in range(1, level):
            total += int(i + 300 * (2 ** (i / 7)))
        return total // 4
    
    xp_needed = xp_for_level(finish_level) - xp_for_level(start_level)
    
    # Approximate GP/XP rates for different methods
    gp_xp_high = 120  # High tier gear
    gp_xp_top = 100   # Top tier gear
    
    cost_high = (xp_needed * gp_xp_high) / 1000000  # Convert to M
    cost_top = (xp_needed * gp_xp_top) / 1000000
    
    embed = create_embed(
        f"⚔️ {skillname.title()} Calculator",
        f"**Start Level:** {start_level}\n**Finish Level:** {finish_level}",
        0x5865F2
    )
    
    embed.add_field(
        name=f"Stats {start_level}-{min(finish_level-1, 85)} With High Tier Gear",
        value=f"🗡️ {start_level}-{min(finish_level, 90)}\n🔥 {gp_xp_high} GP/XP - {xp_needed:,} Exp\n{CURRENCY_EMOJI} {cost_high:.2f}M - 🪙 {cost_high * 0.2:.2f}",
        inline=False
    )
    
    if finish_level > 85:
        embed.add_field(
            name="Stats 85+ With Top Tier Gear",
            value=f"🗡️ 85-{finish_level}\n🔥 {gp_xp_top} GP/XP - {xp_needed:,} Exp\n{CURRENCY_EMOJI} {cost_top:.2f}M - 🪙 {cost_top * 0.2:.2f}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="staff-control-makestaff", description="Make a user staff (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def make_staff(interaction: discord.Interaction, user: discord.Member):
    staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
    if staff_role:
        await user.add_roles(staff_role)
    
    if str(user.id) not in data["staff"]:
        data["staff"].append(str(user.id))
        save_data(data)
    
    await interaction.response.send_message(f"✅ {user.mention} is now Staff member")

@bot.tree.command(name="staff-control-set-deposit", description="Set user deposit (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def set_deposit(interaction: discord.Interaction, user: discord.Member, amount: float):
    wallet = WalletSystem.get_wallet(user.id)
    wallet["deposited"] = amount
    save_data(data)
    
    await interaction.response.send_message(f"✅ {user.mention}'s Deposit is now {format_money(amount)}")

@bot.tree.command(name="staff-listjobstakendeposits", description="List all orders and deposits")
@app_commands.checks.has_permissions(administrator=True)
async def list_orders(interaction: discord.Interaction):
    total_deposit = sum(w.get('deposited', 0) for w in data["wallets"].values())
    active_orders = sum(1 for o in data["orders"].values() if o["status"] != "completed")
    
    embed = create_embed(
        "📊 Orders & Deposit Currently",
        f"Total Deposit: {format_money(total_deposit)}",
        0x5865F2
    )
    embed.add_field(name="Active Orders", value=str(active_orders), inline=True)
    embed.add_field(name="Total Deposit Value", value=format_money(total_deposit), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="setup-application", description="Setup worker application message (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_application(interaction: discord.Interaction, channel: discord.TextChannel = None):
    target_channel = channel or interaction.channel
    
    embed = create_embed(
        "👋 Welcome, sir!",
        "To apply as an OSRS worker, please open a ticket using the button below.",
        0x00FF00
    )
    
    view = ApplicationView()
    await target_channel.send(embed=embed, view=view)
    await interaction.response.send_message(f"Application setup complete in {target_channel.mention}", ephemeral=True)

@bot.tree.command(name="feedback", description="Submit feedback for completed order")
async def feedback_cmd(interaction: discord.Interaction, order_id: int, rating: int, comment: str = None):
    if rating < 1 or rating > 5:
        return await interaction.response.send_message("Rating must be 1-5!", ephemeral=True)
    
    data["feedback"].append({
        "order_id": order_id,
        "user": str(interaction.user.id),
        "rating": rating,
        "comment": comment or "No comment",
        "date": datetime.now().isoformat()
    })
    save_data(data)
    
    # Add bonus
    wallet = WalletSystem.get_wallet(interaction.user.id)
    wallet["balance"] += 10
    save_data(data)
    
    await interaction.response.send_message(
        f"Thank you for your feedback! {CURRENCY_EMOJI} 10M has been added to your wallet!",
        ephemeral=True
    )

# ==================== ERROR HANDLING ====================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Please provide all required arguments!")

# ==================== RUN BOT ====================
if __name__ == "__main__":
    bot.run()