import nextcord
from nextcord.ext import commands, tasks
from nextcord.ui import View, Button, Modal, TextInput, Select, button
from nextcord import Interaction, SlashOption, Permissions, Role, Member, Guild
import aiomysql
import re
import asyncio
from typing import List, Optional, Dict, Any
# I'm literally wayy too fuckin lazy to actually set this up right, so I just hard coded it in
DB_HOST = "x"
DB_PORT = 123
DB_USER = "x"
DB_PASSWORD = "x"
DB_NAME = "x" 


HEX_COLOR_REGEX = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")
MAX_ROLE_NAME_LENGTH = 100


def is_valid_hex_color(color_code: str) -> bool:
    return bool(HEX_COLOR_REGEX.match(color_code))

def convert_hex_to_nextcord_color(hex_code: str) -> nextcord.Color:
    return nextcord.Color(int(hex_code.lstrip('#'), 16))

# --- Views and Modals ---

class EditRoleModal(Modal):
    def __init__(self, current_name: str, current_color: str, edit_type: str):
        super().__init__(f"Edit Your Stylist Role")
        self.edit_type = edit_type
        self.new_value = None

        if self.edit_type == "rename":
            self.role_name_input = TextInput(
                label="New Role Name",
                placeholder="Enter the new name for your role",
                default_value=current_name,
                max_length=MAX_ROLE_NAME_LENGTH,
                required=True
            )
            self.add_item(self.role_name_input)
        elif self.edit_type == "recolor":
            self.role_color_input = TextInput(
                label="New Hex Color Code",
                placeholder="#RRGGBB or #RGB",
                default_value=current_color,
                min_length=4,
                max_length=7,
                required=True
            )
            self.add_item(self.role_color_input)

    async def callback(self, interaction: Interaction):
        if self.edit_type == "rename":
            self.new_value = self.role_name_input.value
        elif self.edit_type == "recolor":
            if not is_valid_hex_color(self.role_color_input.value):
                await interaction.response.send_message("Invalid hex color format. Please use #RRGGBB or #RGB.", ephemeral=True)
                self.stop() 
                return
            self.new_value = self.role_color_input.value
        
        await interaction.response.defer(ephemeral=True) 
        self.stop()


class StylistCog(commands.Cog, name="Stylist"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_pool = None
        self._db_pool_ready = asyncio.Event()
        self.bot.loop.create_task(self._initialize_db_pool())

    async def _initialize_db_pool(self):
        try:
            self.db_pool = await aiomysql.create_pool(
                host=DB_HOST, port=DB_PORT,
                user=DB_USER, password=DB_PASSWORD,
                db=DB_NAME, loop=self.bot.loop,
                autocommit=True
            )
            self._db_pool_ready.set()
            print("StylistCog: Database connection pool created successfully.")
        except Exception as e:
            print(f"StylistCog: Error creating database connection pool: {e}")
            self.db_pool = None 

    async def cog_before_invoke(self, ctx: commands.Context):
        await self._db_pool_ready.wait()
        if not self.db_pool:
            if isinstance(ctx, Interaction): 
                 await ctx.response.send_message(
                    "Database connection is not available. Please try again later.", ephemeral=True
                )
            raise commands.CommandError("Database connection not ready.")

    async def cog_unload(self):
        if self.db_pool:
            self.db_pool.close()
            await self.db_pool.wait_closed()
            print("StylistCog: Database connection pool closed.")

    # --- Database Helper Methods ---
    async def _execute_query(self, query: str, args: tuple = None, fetch_one: bool = False, fetch_all: bool = False, last_row_id: bool = False):
        await self._db_pool_ready.wait()
        if not self.db_pool:
            raise ConnectionError("Database pool is not initialized.")
        
        async with self.db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor if fetch_one or fetch_all else aiomysql.Cursor) as cur:
                await cur.execute(query, args)
                if last_row_id:
                    return cur.lastrowid
                if fetch_one:
                    return await cur.fetchone()
                if fetch_all:
                    return await cur.fetchall()

    async def _ensure_guild_config(self, guild_id: int):
        # This query uses INSERT IGNORE, so duplicate entry warnings are expected if config already exists.
        await self._execute_query(
            """
            INSERT IGNORE INTO stylist_guild_configs (guild_id, allow_boosters)
            VALUES (%s, FALSE)
            """,
            (guild_id,)
        )

    async def get_guild_config(self, guild_id: int) -> Optional[Dict[str, Any]]:
        return await self._execute_query(
            "SELECT guild_id, allow_boosters, created_at, updated_at FROM stylist_guild_configs WHERE guild_id = %s",
            (guild_id,),
            fetch_one=True
        )

    async def update_guild_booster_pref(self, guild_id: int, allow_boosters: bool):
        await self._ensure_guild_config(guild_id)
        await self._execute_query(
            "UPDATE stylist_guild_configs SET allow_boosters = %s WHERE guild_id = %s",
            (allow_boosters, guild_id)
        )

    async def add_permission_role(self, guild_id: int, role_id: int):
        await self._ensure_guild_config(guild_id)
        await self._execute_query(
            "INSERT IGNORE INTO stylist_permission_roles (guild_id, role_id) VALUES (%s, %s)",
            (guild_id, role_id)
        )

    async def remove_permission_role(self, guild_id: int, role_id: int):
        await self._execute_query(
            "DELETE FROM stylist_permission_roles WHERE guild_id = %s AND role_id = %s",
            (guild_id, role_id)
        )

    async def get_permission_roles_ids(self, guild_id: int) -> List[int]:
        roles_data = await self._execute_query(
            "SELECT role_id FROM stylist_permission_roles WHERE guild_id = %s",
            (guild_id,),
            fetch_all=True
        )
        return [row['role_id'] for row in roles_data] if roles_data else []

    async def get_user_custom_role(self, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        # Ensure this table name matches your schema exactly (case-sensitive if your DB is)
        return await self._execute_query(
            """
            SELECT custom_role_id, original_role_name, original_hex_color, created_at 
            FROM stylist_user_custom_roles 
            WHERE user_id = %s AND guild_id = %s
            """,
            (user_id, guild_id),
            fetch_one=True
        )
    
    async def get_user_custom_role_by_role_id(self, custom_role_id: int) -> Optional[Dict[str, Any]]:
        return await self._execute_query(
            """
            SELECT user_id, guild_id, original_role_name, original_hex_color
            FROM stylist_user_custom_roles
            WHERE custom_role_id = %s
            """,
            (custom_role_id,),
            fetch_one=True
        )

    async def create_user_custom_role(self, user_id: int, guild_id: int, custom_role_id: int, role_name: str, hex_color: str):
        await self._ensure_guild_config(guild_id)
        await self._execute_query(
            """
            INSERT INTO stylist_user_custom_roles 
            (user_id, guild_id, custom_role_id, original_role_name, original_hex_color) 
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, guild_id, custom_role_id, role_name, hex_color)
        )

    async def update_user_custom_role_details(self, user_id: int, guild_id: int, new_name: Optional[str] = None, new_color: Optional[str] = None):
        if not new_name and not new_color:
            return

        updates = []
        params = []
        if new_name:
            updates.append("original_role_name = %s")
            params.append(new_name)
        if new_color:
            updates.append("original_hex_color = %s")
            params.append(new_color)
        
        params.extend([user_id, guild_id])
        
        await self._execute_query(
            f"UPDATE stylist_user_custom_roles SET {', '.join(updates)} WHERE user_id = %s AND guild_id = %s",
            tuple(params)
        )

    async def delete_user_custom_role(self, user_id: int, guild_id: int):
        await self._execute_query(
            "DELETE FROM stylist_user_custom_roles WHERE user_id = %s AND guild_id = %s",
            (user_id, guild_id)
        )

    async def delete_user_custom_role_by_role_id(self, custom_role_id: int):
         await self._execute_query(
            "DELETE FROM stylist_user_custom_roles WHERE custom_role_id = %s",
            (custom_role_id,)
        )

    # --- Permission Check Helper ---
    async def _is_guild_configured(self, guild_id: int) -> bool:
        config = await self.get_guild_config(guild_id)
        return config is not None

    async def _has_stylist_permission(self, interaction: Interaction) -> bool:
        if not interaction.guild or not interaction.user: 
            return False
        
        member = interaction.guild.get_member(interaction.user.id) 
        if not member: 
            return False 

        if interaction.guild.owner_id == member.id:
            return True
        if member.guild_permissions.administrator: 
            return True

        guild_config = await self.get_guild_config(interaction.guild.id)
        if not guild_config: 
            return False 

        permission_role_ids = await self.get_permission_roles_ids(interaction.guild.id)
        member_role_ids = {role.id for role in member.roles} 
        if any(pid in member_role_ids for pid in permission_role_ids):
            return True

        if guild_config.get('allow_boosters', False):
            if member.premium_since is not None: 
                 return True
        return False

    # --- Slash Command Group ---
    stylist = SlashOption(
        name="stylist",
        description="Stylist commands to manage custom roles."
    )

    # --- Config Subcommand Group ---
    @nextcord.slash_command(name="stylist", description="Base command for stylist features.")
    async def stylist_base(self, interaction: Interaction):
        pass

    @stylist_base.subcommand(name="config", description="Configure Stylist settings for this server.")
    async def stylist_config(self, interaction: Interaction):
        if not isinstance(interaction.user, nextcord.Member):
            await interaction.response.send_message("Could not verify permissions.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You must be an administrator to use this command.", ephemeral=True
            )
            return

        await self._db_pool_ready.wait()
        if not self.db_pool:
            await interaction.response.send_message("Database connection is not ready. Please try again.", ephemeral=True)
            return

        await self._ensure_guild_config(interaction.guild.id) 
        guild_config = await self.get_guild_config(interaction.guild.id)
        perm_role_ids = await self.get_permission_roles_ids(interaction.guild.id)
        
        perm_roles_mentions = []
        for role_id in perm_role_ids:
            role = interaction.guild.get_role(role_id)
            perm_roles_mentions.append(role.mention if role else f"ID: {role_id} (deleted)")

        embed = nextcord.Embed(
            title="Stylist Configuration",
            description="Manage settings for the Stylist feature.",
            color=nextcord.Color.blue()
        )
        embed.add_field(name="Allow Server Boosters", value="✅ Yes" if guild_config.get('allow_boosters') else "❌ No", inline=False)
        embed.add_field(name="Permission Roles", value=", ".join(perm_roles_mentions) if perm_roles_mentions else "None set", inline=False)

        view = StylistConfigView(self, interaction.guild.id, guild_config.get('allow_boosters', False), perm_role_ids)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # --- User Commands ---
    @stylist_base.subcommand(name="create", description="Create your personal stylist role.")
    async def stylist_create(
        self,
        interaction: Interaction,
        role_name: str = SlashOption(description="Name for your custom role.", required=True, max_length=MAX_ROLE_NAME_LENGTH),
        hex_color: str = SlashOption(description="Hex color code for your role (e.g., #FF00FF).", required=True)
    ):
        # Initial checks that respond directly
        await self._db_pool_ready.wait()
        if not self.db_pool:
            await interaction.response.send_message("Database connection is not ready. Please try again.", ephemeral=True)
            return

        if not await self._is_guild_configured(interaction.guild.id):
            await interaction.response.send_message(
                "This feature is not configured for this server. Please ask an administrator to configure it using `/stylist config`.",
                ephemeral=True
            )
            return

        if not await self._has_stylist_permission(interaction):
            await interaction.response.send_message(
                "You do not have permission to use this command. You might need a specific role or be a server booster (if enabled).",
                ephemeral=True
            )
            return

        if not is_valid_hex_color(hex_color):
            await interaction.response.send_message("Invalid hex color format. Please use #RRGGBB or #RGB (e.g., #AA33FF).", ephemeral=True)
            return
        
        if len(role_name) > MAX_ROLE_NAME_LENGTH:
             await interaction.response.send_message(f"Role name cannot exceed {MAX_ROLE_NAME_LENGTH} characters.", ephemeral=True)
             return

        existing_custom_role = await self.get_user_custom_role(interaction.user.id, interaction.guild.id)
        if existing_custom_role:
            await interaction.response.send_message("You already have a custom stylist role. Use `/stylist edit` to modify or delete it.", ephemeral=True)
            return

        # Defer the interaction response before potentially slow operations
        await interaction.response.defer(ephemeral=True)

        try:
            if not interaction.guild.me.guild_permissions.manage_roles:
                await interaction.followup.send("I don't have the 'Manage Roles' permission to create your role.", ephemeral=True)
                return

            new_role_color = convert_hex_to_nextcord_color(hex_color)
            bot_member = interaction.guild.me
            position = bot_member.top_role.position -1 if bot_member.top_role and bot_member.top_role.position > 0 else 1

            discord_role = await interaction.guild.create_role(
                name=role_name,
                color=new_role_color,
                permissions=Permissions.none(), 
                reason=f"Stylist custom role for {interaction.user.name}"
            )
            try:
                await discord_role.edit(position=max(1, position))
            except nextcord.Forbidden:
                print(f"StylistCog: Could not set position for role {discord_role.id} in guild {interaction.guild.id} (Forbidden).")
                pass 
            except nextcord.HTTPException as he:
                print(f"StylistCog: HTTP error setting position for role {discord_role.id} in guild {interaction.guild.id}: {he}")
                pass


            await self.create_user_custom_role(interaction.user.id, interaction.guild.id, discord_role.id, role_name, hex_color)
            
            member = interaction.guild.get_member(interaction.user.id)
            if member:
                await member.add_roles(discord_role, reason="Stylist role created and assigned.")
            
            await interaction.followup.send(f"Successfully created and equipped your custom role: {discord_role.mention}!", ephemeral=True)

        except nextcord.Forbidden:
            await interaction.followup.send("I lack permissions to create roles or assign them. Please check my 'Manage Roles' permission.", ephemeral=True)
        except Exception as e:
            print(f"Error in stylist_create: {e}")
            await interaction.followup.send("An error occurred while creating your role. Please try again later.", ephemeral=True)


    @stylist_base.subcommand(name="edit", description="Edit or manage your personal stylist role.")
    async def stylist_edit(self, interaction: Interaction):
        await self._db_pool_ready.wait()
        if not self.db_pool:
            await interaction.response.send_message("Database connection is not ready. Please try again.", ephemeral=True)
            return

        if not await self._is_guild_configured(interaction.guild.id):
            await interaction.response.send_message(
                "This feature is not configured for this server. Please ask an administrator to configure it.",
                ephemeral=True
            )
            return
        
        if not await self._has_stylist_permission(interaction): 
            await interaction.response.send_message(
                "You currently don't have permission to manage stylist roles.",
                ephemeral=True
            )
            return
        
        # Defer interaction before DB calls and view creation
        await interaction.response.defer(ephemeral=True)

        custom_role_data = await self.get_user_custom_role(interaction.user.id, interaction.guild.id)
        if not custom_role_data:
            await interaction.followup.send("You don't have a custom stylist role to edit. Use `/stylist create` to make one.", ephemeral=True)
            return

        role_id = custom_role_data['custom_role_id']
        role_name = custom_role_data['original_role_name']
        hex_color = custom_role_data['original_hex_color']
        
        discord_role = interaction.guild.get_role(role_id)

        if not discord_role:
            await interaction.followup.send(
                "Your custom role seems to have been deleted from the server. I'll clean up the database entry. "
                "You can create a new one using `/stylist create`.",
                ephemeral=True
            )
            await self.delete_user_custom_role(interaction.user.id, interaction.guild.id)
            return

        embed = nextcord.Embed(
            title="Manage Your Stylist Role",
            description=f"Role: {discord_role.mention}\nName: `{role_name}`\nColor: `{hex_color}`",
            color=discord_role.color
        )
        member = interaction.guild.get_member(interaction.user.id)
        is_wearing = discord_role in member.roles if member else False

        view = StylistEditView(self, interaction, discord_role, role_name, hex_color, is_wearing)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # --- Event Listeners ---
    @commands.Cog.listener()
    async def on_member_update(self, before: Member, after: Member):
        await self._db_pool_ready.wait()
        if not self.db_pool: return 

        if before.roles == after.roles and before.premium_since == after.premium_since:
            return

        guild_id = after.guild.id
        user_id = after.id

        custom_role_data = await self.get_user_custom_role(user_id, guild_id)
        if not custom_role_data:
            return 

        async def _check_permission_for_event(member_obj: Member, guild_config_obj: Dict) -> bool:
            if member_obj.guild.owner_id == member_obj.id or member_obj.guild_permissions.administrator:
                return True
            
            permission_role_ids_list = await self.get_permission_roles_ids(member_obj.guild.id)
            member_role_ids_set = {role.id for role in member_obj.roles}
            if any(pid in member_role_ids_set for pid in permission_role_ids_list):
                return True
            
            if guild_config_obj.get('allow_boosters', False) and member_obj.premium_since is not None:
                return True
            return False

        guild_config = await self.get_guild_config(guild_id)
        if not guild_config: 
            return

        still_has_permission = await _check_permission_for_event(after, guild_config)

        if not still_has_permission:
            custom_role_id = custom_role_data['custom_role_id']
            role_to_delete = after.guild.get_role(custom_role_id)
            
            print(f"User {after.name} (ID: {user_id}) lost stylist permissions in guild {guild_id}. Deleting role ID {custom_role_id}.")

            if role_to_delete:
                try:
                    await role_to_delete.delete(reason="User lost stylist permissions.")
                    print(f"Deleted role {role_to_delete.name} from Discord server {guild_id}.")
                except nextcord.Forbidden:
                    print(f"Failed to delete role {custom_role_id} from Discord (Forbidden) for user {user_id} in guild {guild_id}.")
                except nextcord.HTTPException as e:
                    print(f"Failed to delete role {custom_role_id} from Discord (HTTP {e.status}) for user {user_id} in guild {guild_id}.")
            
            await self.delete_user_custom_role_by_role_id(custom_role_id)
            print(f"Deleted stylist role {custom_role_id} from DB for user {user_id} in guild {guild_id}.")


    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: Role):
        await self._db_pool_ready.wait()
        if not self.db_pool: return

        custom_role_data = await self.get_user_custom_role_by_role_id(role.id)
        if custom_role_data:
            print(f"Stylist role '{custom_role_data['original_role_name']}' (ID: {role.id}) was deleted from guild {role.guild.id}. Removing from DB.")
            await self.delete_user_custom_role_by_role_id(role.id)


# --- Views for Config and Edit ---
class StylistConfigView(View):
    def __init__(self, cog: StylistCog, guild_id: int, current_booster_pref: bool, current_perm_roles: List[int]):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.current_booster_pref = current_booster_pref
        self.current_perm_roles_ids = current_perm_roles 
        
        self.booster_button = Button(label=f"Boosters: {'Disallow' if current_booster_pref else 'Allow'} Perks", 
                                     style=nextcord.ButtonStyle.danger if current_booster_pref else nextcord.ButtonStyle.success,
                                     custom_id="toggle_booster_stylist")
        self.booster_button.callback = self.toggle_booster_callback
        self.add_item(self.booster_button)

        self.add_item(RoleSelect(cog, guild_id, self.current_perm_roles_ids, "add", placeholder="Add a permission role..."))
        if current_perm_roles: 
            self.add_item(RoleSelect(cog, guild_id, self.current_perm_roles_ids, "remove", placeholder="Remove a permission role..."))

    async def toggle_booster_callback(self, interaction: Interaction):
        # Defer immediately as this is a component interaction
        # await interaction.response.defer() # update_embed will handle the response by editing.

        new_pref = not self.current_booster_pref
        await self.cog.update_guild_booster_pref(self.guild_id, new_pref)
        await self.update_embed(interaction) # This will edit the original message

    async def update_embed(self, interaction: Interaction):
        guild_config = await self.cog.get_guild_config(self.guild_id)
        perm_role_ids = await self.cog.get_permission_roles_ids(self.guild_id)
        
        self.current_booster_pref = guild_config.get('allow_boosters', False)
        self.current_perm_roles_ids = perm_role_ids

        perm_roles_mentions = []
        for role_id in perm_role_ids:
            role = interaction.guild.get_role(role_id) 
            perm_roles_mentions.append(role.mention if role else f"ID: {role_id} (deleted)")

        embed = nextcord.Embed(
            title="Stylist Configuration Updated", 
            description="Manage settings for the Stylist feature.",
            color=nextcord.Color.green() 
        )
        embed.add_field(name="Allow Server Boosters", value="✅ Yes" if self.current_booster_pref else "❌ No", inline=False)
        embed.add_field(name="Permission Roles", value=", ".join(perm_roles_mentions) if perm_roles_mentions else "None set", inline=False)
        
        self.clear_items() 
        self.booster_button = Button(label=f"Boosters: {'Disallow' if self.current_booster_pref else 'Allow'} Perks", 
                                     style=nextcord.ButtonStyle.danger if self.current_booster_pref else nextcord.ButtonStyle.success,
                                     custom_id="toggle_booster_stylist") 
        self.booster_button.callback = self.toggle_booster_callback 
        self.add_item(self.booster_button)
        
        self.add_item(RoleSelect(self.cog, self.guild_id, self.current_perm_roles_ids, "add", placeholder="Add a permission role..."))
        if self.current_perm_roles_ids: 
            self.add_item(RoleSelect(self.cog, self.guild_id, self.current_perm_roles_ids, "remove", placeholder="Remove a permission role..."))
        
        try:
            if not interaction.response.is_done():
                # This is the primary response for the component interaction that triggered this update
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                # If already responded (e.g., deferred by a higher level command), use followup or original message edit
                await interaction.edit_original_message(embed=embed, view=self)
        except nextcord.NotFound:
            print("Failed to edit message in update_embed, message not found.")
        except Exception as e:
            print(f"Error editing message in update_embed: {e}")


class RoleSelect(nextcord.ui.RoleSelect):
    def __init__(self, cog: StylistCog, guild_id: int, current_perm_roles_ids: List[int], action: str, placeholder: str):
        # Ensure custom_id is unique if multiple instances of this view/select can exist simultaneously
        # Adding timestamp is a common way to achieve this for dynamic views.
        super().__init__(
            placeholder=placeholder, 
            min_values=1, 
            max_values=1, 
            custom_id=f"stylist_config_role_select_{action}_{nextcord.utils.utcnow().timestamp()}" 
        )
        self.cog = cog
        self.guild_id = guild_id
        self.current_perm_roles_ids_on_init = list(current_perm_roles_ids) 
        self.action = action 

        if action == "remove":
            options = []
            guild = cog.bot.get_guild(guild_id) 
            if guild:
                for role_id in self.current_perm_roles_ids_on_init:
                    role = guild.get_role(role_id)
                    if role:
                        # For RoleSelect, the value of SelectOption should be the Role object itself if you want self.values to return Role objects.
                        # If you set value=str(role.id), then self.values[0] will be a string.
                        # Let's keep it as string for now as the callback handles int conversion.
                        options.append(nextcord.SelectOption(label=role.name, value=str(role.id), description=f"ID: {role.id}"))
            
            if not options: 
                self.disabled = True
                # Provide a placeholder option if disabled, as an empty options list can cause issues.
                self.options = [nextcord.SelectOption(label="No roles to remove", value="disabled_placeholder")]
            else:
                self.options = options
        # For "add" action, RoleSelect automatically populates with all server roles.
        # The values returned will be Role objects.

    async def callback(self, interaction: Interaction):
        selected_item = self.values[0] # This will be a Role object for 'add', or string for 'remove' if populated with str(role.id)

        if isinstance(selected_item, str) and selected_item == "disabled_placeholder":
            await interaction.response.send_message("There are no roles to remove or action is invalid.", ephemeral=True)
            return
        
        if isinstance(selected_item, nextcord.Role):
            selected_role_id = selected_item.id
        elif isinstance(selected_item, str): # From 'remove' select where value is str(role.id)
            try:
                selected_role_id = int(selected_item)
            except ValueError:
                await interaction.response.send_message("Invalid role selection value.", ephemeral=True)
                return
        else:
            await interaction.response.send_message("Unexpected selection type.", ephemeral=True)
            return

        latest_perm_roles_ids = await self.cog.get_permission_roles_ids(self.guild_id)
        
        action_taken_requires_view_update = False
        if self.action == "add":
            if selected_role_id in latest_perm_roles_ids:
                await interaction.response.send_message(f"Role <@&{selected_role_id}> is already a permission role.", ephemeral=True)
                return 
            await self.cog.add_permission_role(self.guild_id, selected_role_id)
            action_taken_requires_view_update = True
        elif self.action == "remove":
            if selected_role_id not in latest_perm_roles_ids: 
                await interaction.response.send_message(f"Role <@&{selected_role_id}> is not a permission role or was already removed.", ephemeral=True)
                # Still update view to ensure consistency if it was removed by another means
            else:
                await self.cog.remove_permission_role(self.guild_id, selected_role_id)
            action_taken_requires_view_update = True 
        
        if action_taken_requires_view_update and isinstance(self.view, StylistConfigView):
            try:
                # update_embed will handle responding by editing the message
                await self.view.update_embed(interaction)
            except Exception as e:
                print(f"Error in RoleSelect.callback calling update_embed: {e}")
                # Fallback if update_embed fails before responding
                if not interaction.response.is_done():
                    await interaction.response.send_message("An error occurred while updating the configuration.", ephemeral=True)
        elif not interaction.response.is_done():
            # If no action requiring view update was taken AND we haven't responded yet
            # (e.g. an error message was already sent, or this path shouldn't be hit)
            # This defer is a safety net.
            await interaction.response.defer(ephemeral=True)


class StylistEditView(View):
    def __init__(self, cog: StylistCog, original_interaction: Interaction, discord_role: Role, current_name: str, current_color: str, is_wearing: bool):
        # original_interaction is the interaction from the /stylist edit command.
        # We need to use its followup/edit_original_message for final responses.
        # Component interactions within this view (buttons, modals) will have their own interaction objects.
        super().__init__(timeout=180)
        self.cog = cog
        self.original_command_interaction = original_interaction # Store the initial command's interaction
        self.user_id = original_interaction.user.id
        self.guild_id = original_interaction.guild.id
        self.discord_role = discord_role # This is the Role object
        self.current_name = current_name
        self.current_color = current_color
        self.is_wearing = is_wearing

        self.wear_button = self.create_wear_button() 
        self.add_item(self.wear_button)


    def create_wear_button(self):
        label = "Unwear Role" if self.is_wearing else "Wear Role"
        style = nextcord.ButtonStyle.secondary if self.is_wearing else nextcord.ButtonStyle.primary
        button_item = Button(label=label, style=style, custom_id="stylist_toggle_wear")
        button_item.callback = self.toggle_wear_button 
        return button_item

    @button(label="Rename Role", style=nextcord.ButtonStyle.blurple, custom_id="stylist_rename")
    async def rename_role_button(self, button_obj: Button, interaction: Interaction): # interaction here is for the button click
        modal = EditRoleModal(self.current_name, self.current_color, "rename")
        await interaction.response.send_modal(modal) # Respond to button click by sending modal
        await modal.wait() 

        if modal.new_value is not None:
            new_name = modal.new_value
            try:
                await self.discord_role.edit(name=new_name, reason=f"Stylist role rename by user {interaction.user.name}")
                await self.cog.update_user_custom_role_details(self.user_id, self.guild_id, new_name=new_name)
                self.current_name = new_name
                # Edit the message that this view is attached to
                await self.original_command_interaction.edit_original_message(content=f"Role renamed to '{new_name}'.", embed=self._build_updated_embed(), view=self)
            except nextcord.Forbidden:
                await self.original_command_interaction.edit_original_message(content="I lack permissions to rename the role.", embed=None, view=None)
            except Exception as e:
                print(f"Error renaming role: {e}")
                await self.original_command_interaction.edit_original_message(content="An error occurred while renaming.", embed=None, view=None)

    @button(label="Recolor Role", style=nextcord.ButtonStyle.blurple, custom_id="stylist_recolor")
    async def recolor_role_button(self, button_obj: Button, interaction: Interaction): # interaction here is for the button click
        modal = EditRoleModal(self.current_name, self.current_color, "recolor")
        await interaction.response.send_modal(modal) # Respond to button click
        await modal.wait()

        if modal.new_value is not None:
            new_color_hex = modal.new_value
            try:
                new_nextcord_color = convert_hex_to_nextcord_color(new_color_hex)
                await self.discord_role.edit(color=new_nextcord_color, reason=f"Stylist role recolor by user {interaction.user.name}")
                await self.cog.update_user_custom_role_details(self.user_id, self.guild_id, new_color=new_color_hex)
                self.current_color = new_color_hex
                await self.original_command_interaction.edit_original_message(content=f"Role color changed to `{new_color_hex}`.", embed=self._build_updated_embed(), view=self)
            except nextcord.Forbidden:
                await self.original_command_interaction.edit_original_message(content="I lack permissions to edit the role color.", embed=None, view=None)
            except Exception as e:
                print(f"Error recoloring role: {e}")
                await self.original_command_interaction.edit_original_message(content="An error occurred while recoloring.", embed=None, view=None)

    async def toggle_wear_button(self, interaction: Interaction): # interaction here is for the button click
        member = interaction.guild.get_member(self.user_id)
        if not member:
            await interaction.response.send_message("Could not find you as a member in this server.", ephemeral=True)
            return

        action_message = ""
        try:
            if self.discord_role in member.roles: 
                await member.remove_roles(self.discord_role, reason="Stylist role unequipped by user.")
                self.is_wearing = False
                action_message = "Role unequipped."
            else: 
                await member.add_roles(self.discord_role, reason="Stylist role equipped by user.")
                self.is_wearing = True
                action_message = "Role equipped."
            
            self.wear_button.label = "Unwear Role" if self.is_wearing else "Wear Role"
            self.wear_button.style = nextcord.ButtonStyle.secondary if self.is_wearing else nextcord.ButtonStyle.primary
            
            # Respond to the button click by editing the message this view is attached to
            await interaction.response.edit_message(content=action_message, embed=self._build_updated_embed(), view=self)
        except nextcord.Forbidden:
            # Ensure we respond if not already done
            if not interaction.response.is_done():
                await interaction.response.send_message("I lack permissions to modify your roles.", ephemeral=True)
            else: 
                await interaction.followup.send("I lack permissions to modify your roles.", ephemeral=True)
        except Exception as e:
            print(f"Error toggling role wear: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("An error occurred.", ephemeral=True)
            else:
                await interaction.followup.send("An error occurred.", ephemeral=True)


    @button(label="Delete Role", style=nextcord.ButtonStyle.danger, custom_id="stylist_delete")
    async def delete_role_button(self, button_obj: Button, interaction: Interaction): # interaction here is for the button click
        #Defer the button click interaction first
        await interaction.response.defer(ephemeral=True) 

        try:
            await self.discord_role.delete(reason=f"Stylist role deleted by user {interaction.user.name}")
        except nextcord.Forbidden:
            await interaction.followup.send("I lack permissions to delete the role from Discord.", ephemeral=True)
        except nextcord.NotFound:
            pass 
        except Exception as e:
            print(f"Error deleting Discord role: {e}")
            await interaction.followup.send("An error occurred while deleting the role from Discord.", ephemeral=True)
            #Don't return, still try to delete from DB

        try:
            await self.cog.delete_user_custom_role(self.user_id, self.guild_id)
            await self.original_command_interaction.edit_original_message(content="Your custom stylist role has been deleted from the server and database.", embed=None, view=None)
            self.stop() 
        except Exception as e:
            print(f"Error deleting role from DB: {e}")
            await interaction.followup.send("Deleted role from Discord (if possible), but failed to remove from database. Please contact support.", ephemeral=True)


    def _build_updated_embed(self) -> nextcord.Embed:
        role_mention = "Role Deleted/Invalid"
        role_color = convert_hex_to_nextcord_color(self.current_color) 
        
        if self.discord_role and isinstance(self.discord_role, nextcord.Role):
            # Use original_command_interaction.guild to get the rol
            refetched_role = self.original_command_interaction.guild.get_role(self.discord_role.id)
            if refetched_role:
                role_mention = refetched_role.mention
                role_color = refetched_role.color
            else: 
                role_mention = f"{self.current_name} (Deleted from server)"

        embed = nextcord.Embed(
            title="Manage Your Stylist Role",
            description=f"Role: {role_mention}\nName: `{self.current_name}`\nColor: `{self.current_color}`",
            color=role_color
        )
        return embed

    async def on_timeout(self):
        try:
            if self.original_command_interaction and self.original_command_interaction.message:
                message = await self.original_command_interaction.channel.fetch_message(self.original_command_interaction.message.id)
                if message and message.view and hasattr(message.view, 'id') and hasattr(self, 'id') and message.view.id == self.id:
                    await self.original_command_interaction.edit_original_message(content="Stylist edit session timed out.", view=None)
                elif message and not message.view: 
                    pass
        except nextcord.NotFound:
            pass 
        except AttributeError: 
            pass 
        except Exception as e:
            print(f"Error on StylistEditView timeout: {e}")


def setup(bot: commands.Bot):
    bot.add_cog(StylistCog(bot))
