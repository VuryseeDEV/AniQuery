import mysql.connector
from mysql.connector import pooling
import os
from dotenv import load_dotenv
import asyncio
import json

class DatabaseManager:
    def __init__(self, bot=None):
        self.bot = bot
        load_dotenv()
        
        
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'animebot'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_NAME', 'anime_bot'),
            'raise_on_warnings': True
        }
        
        
        try:
            self.pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="anime_bot_pool",
                pool_size=20,  
                **self.db_config
            )
            self._last_conn_error = None  
            print(f"✅ Connected to MySQL pool for {self.db_config['database']}")
        except Exception as e:
            print(f"❌ Database connection pool error: {e}")
            self.pool = None
    
    def get_connection(self):
        """Get a connection from the pool"""
        try:
            if self.pool:
                return self.pool.get_connection()
            else:
                
                return mysql.connector.connect(**self.db_config)
        except Exception as e:
            
            error_msg = str(e)
            if not hasattr(self, '_last_conn_error') or self._last_conn_error != error_msg:
                print(f"Database connection error: {e}")
                self._last_conn_error = error_msg
            return None
    
    async def execute_query(self, query, params=None, fetch=False, many=False):
        """
        Execute a query and optionally fetch results
        
        Args:
            query (str): SQL query to execute
            params (tuple|list|dict): Parameters for the query
            fetch (bool): Whether to fetch results
            many (bool): Whether to executemany (for bulk operations)
            
        Returns:
            list|int: Query results if fetch=True, otherwise number of affected rows
        """
        
        return await asyncio.to_thread(self._execute_query_sync, query, params, fetch, many)
    
    def _execute_query_sync(self, query, params=None, fetch=False, many=False):
        """Synchronous version of execute_query for use with asyncio.to_thread"""
        conn = self.get_connection()
        if not conn:
            return None
            
        try:
            cursor = conn.cursor(dictionary=True)
            
            if many and params:
                cursor.executemany(query, params)
            else:
                cursor.execute(query, params or ())
            
            if fetch:
                result = cursor.fetchall()
            else:
                conn.commit()
                result = cursor.rowcount
                
            return result
        except mysql.connector.errors.IntegrityError as e:
            
            if "Duplicate entry" in str(e):
                conn.rollback()
                return 0
            else:
                print(f"Integrity error: {e}")
                print(f"Query: {query}")
                print(f"Params: {params}")
                return None
        except Exception as e:
            print(f"Query execution error: {e}")
            print(f"Query: {query}")
            print(f"Params: {params}")
            return None
        finally:
            if 'cursor' in locals():
                cursor.close()
            conn.close()
    
    
    async def add_subscription(self, user_id, anime_id, anime_title):
        """Add a subscription with updated MySQL syntax"""
        try:
            
            exists_query = "SELECT id FROM subscriptions WHERE user_id = %s AND anime_id = %s"
            result = await self.execute_query(exists_query, (user_id, anime_id), fetch=True)
            
            if result:
                
                update_query = """
                UPDATE subscriptions SET
                    anime_title = %s
                WHERE user_id = %s AND anime_id = %s
                """
                
                return await self.execute_query(update_query, (anime_title, user_id, anime_id))
            else:
                
                insert_query = """
                INSERT INTO subscriptions (user_id, anime_id, anime_title)
                VALUES (%s, %s, %s)
                """
                
                return await self.execute_query(insert_query, (user_id, anime_id, anime_title))
        except Exception as e:
            print(f"Error adding subscription: {e}")
            return None
    
    
    async def get_user_subscriptions(self, user_id):
        """Get all subscriptions for a user"""
        try:
            
            query = "SELECT * FROM subscriptions WHERE user_id = %s ORDER BY anime_title"
            result = await self.execute_query(query, (user_id,), fetch=True)
            return result or []
        except Exception as e:
            print(f"Error retrieving subscriptions: {e}")
            
            return []
    async def remove_subscription(self, user_id, anime_id):
        """Remove a subscription"""
        try:
            query = "DELETE FROM subscriptions WHERE user_id = %s AND anime_id = %s"
            return await self.execute_query(query, (user_id, anime_id))
        except Exception as e:
            print(f"Error removing subscription: {e}")
            return None
    async def get_anime_subscribers(self, anime_id):
        query = "SELECT user_id FROM subscriptions WHERE anime_id = %s"
        return await self.execute_query(query, (anime_id,), fetch=True)
    
    
    async def add_notification(self, user_id, anime_id, episode, successful=True):
        """Add a notification with updated MySQL syntax"""
        try:
            
            exists_query = """
            SELECT id FROM notification_history 
            WHERE user_id = %s AND anime_id = %s AND episode_number = %s
            """
            result = await self.execute_query(exists_query, (user_id, anime_id, episode), fetch=True)
            
            if result:
                
                update_query = """
                UPDATE notification_history SET
                    timestamp = CURRENT_TIMESTAMP,
                    successful = %s
                WHERE user_id = %s AND anime_id = %s AND episode_number = %s
                """
                
                return await self.execute_query(update_query, (successful, user_id, anime_id, episode))
            else:
                
                insert_query = """
                INSERT INTO notification_history (user_id, anime_id, episode_number, successful)
                VALUES (%s, %s, %s, %s)
                """
                
                return await self.execute_query(insert_query, (user_id, anime_id, episode, successful))
        except Exception as e:
            print(f"Error adding notification: {e}")
            return None
    
    
    async def cache_anime(self, anime_data):
        """Cache anime data with updated MySQL syntax"""
        try:
            
            exists_query = "SELECT anime_id FROM anime_cache WHERE anime_id = %s"
            result = await self.execute_query(exists_query, (anime_data['id'],), fetch=True)
            
            
            import json
            genres_json = json.dumps(anime_data.get('genres', []))
            
            if result:
                
                update_query = """
                UPDATE anime_cache SET
                    title_romaji = %s,
                    title_english = %s,
                    description = %s,
                    cover_image_url = %s,
                    status = %s,
                    format = %s,
                    episodes = %s,
                    season = %s,
                    season_year = %s,
                    genres = %s,
                    site_url = %s,
                    last_updated = CURRENT_TIMESTAMP
                WHERE anime_id = %s
                """
                
                params = (
                    anime_data['title']['romaji'],
                    anime_data['title'].get('english'),
                    anime_data.get('description'),
                    anime_data.get('coverImage', {}).get('large'),
                    anime_data.get('status'),
                    anime_data.get('format'),
                    anime_data.get('episodes'),
                    anime_data.get('season'),
                    anime_data.get('seasonYear'),
                    genres_json,
                    anime_data.get('siteUrl'),
                    anime_data['id']
                )
                
                return await self.execute_query(update_query, params)
            else:
                
                insert_query = """
                INSERT INTO anime_cache (
                    anime_id, title_romaji, title_english, description, 
                    cover_image_url, status, format, episodes, 
                    season, season_year, genres, site_url
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                params = (
                    anime_data['id'],
                    anime_data['title']['romaji'],
                    anime_data['title'].get('english'),
                    anime_data.get('description'),
                    anime_data.get('coverImage', {}).get('large'),
                    anime_data.get('status'),
                    anime_data.get('format'),
                    anime_data.get('episodes'),
                    anime_data.get('season'),
                    anime_data.get('seasonYear'),
                    genres_json,
                    anime_data.get('siteUrl')
                )
                
                return await self.execute_query(insert_query, params)
        except Exception as e:
            print(f"Error caching anime data: {e}")
            return None

    
    async def get_cached_anime(self, anime_id):
        query = "SELECT * FROM anime_cache WHERE anime_id = %s"
        result = await self.execute_query(query, (anime_id,), fetch=True)
        return result[0] if result else None
    
    
    async def update_airing_schedule(self, anime_id, episode, airing_at):
        """Update airing schedule with updated MySQL syntax"""
        try:
            
            exists_query = "SELECT id FROM airing_schedule WHERE anime_id = %s AND episode = %s"
            result = await self.execute_query(exists_query, (anime_id, episode), fetch=True)
            
            if result:
                
                update_query = """
                UPDATE airing_schedule SET
                    airing_at = %s
                WHERE anime_id = %s AND episode = %s
                """
                
                return await self.execute_query(update_query, (airing_at, anime_id, episode))
            else:
                
                insert_query = """
                INSERT INTO airing_schedule (anime_id, episode, airing_at)
                VALUES (%s, %s, %s)
                """
                
                return await self.execute_query(insert_query, (anime_id, episode, airing_at))
        except Exception as e:
            print(f"Error updating airing schedule: {e}")
            return None
    
    async def get_upcoming_episodes(self, start_time, end_time):
        query = """
        SELECT a.*, c.title_romaji, c.title_english, c.cover_image_url, c.site_url
        FROM airing_schedule a
        JOIN anime_cache c ON a.anime_id = c.anime_id
        WHERE a.airing_at >= %s AND a.airing_at <= %s
        ORDER BY a.airing_at
        """
        return await self.execute_query(query, (start_time, end_time), fetch=True)
    
    async def get_recently_aired(self, hours_ago=1):
        """Get episodes that aired within the last X hours"""
        import time
        now = int(time.time())
        hours_ago_timestamp = now - (hours_ago * 3600)
        
        query = """
        SELECT a.*, c.title_romaji, c.title_english, c.cover_image_url, c.site_url
        FROM airing_schedule a
        JOIN anime_cache c ON a.anime_id = c.anime_id
        WHERE a.airing_at >= %s AND a.airing_at <= %s
        ORDER BY a.airing_at
        """
        return await self.execute_query(query, (hours_ago_timestamp, now), fetch=True)
    
    
    async def get_user_settings(self, user_id):
        query = "SELECT * FROM user_settings WHERE user_id = %s"
        result = await self.execute_query(query, (user_id,), fetch=True)
        
        if not result:
            
            await self.execute_query(
                "INSERT INTO user_settings (user_id) VALUES (%s)",
                (user_id,)
            )
            return {"user_id": user_id, "notification_enabled": True, "preferred_title_format": "romaji"}
        
        return result[0]
    
    async def update_user_settings(self, user_id, notification_enabled=None, preferred_title_format=None):
        updates = []
        params = [user_id]
        
        if notification_enabled is not None:
            updates.append("notification_enabled = %s")
            params.append(notification_enabled)
            
        if preferred_title_format is not None:
            updates.append("preferred_title_format = %s")
            params.append(preferred_title_format)
            
        if not updates:
            return False
            
        fields = []
        values = []
        update_parts = []
        
        for update in updates:
            field = update.split(' = ')[0]
            fields.append(field)
            update_parts.append(f"{field} = new_data.{field}")
        
        query = f"""
        INSERT INTO user_settings (user_id, {', '.join(fields)})
        VALUES ({', '.join(['%s'] * (1 + len(fields)))}) AS new_data
        ON DUPLICATE KEY UPDATE {', '.join(update_parts)}
        """
        
        return await self.execute_query(query, params)
    
    
    async def get_guild_settings(self, guild_id):
        query = "SELECT * FROM guild_settings WHERE guild_id = %s"
        result = await self.execute_query(query, (guild_id,), fetch=True)
        
        if not result:
            return {"guild_id": guild_id, "notification_channel_id": None, "public_notifications": False}
        
        return result[0]
    
    async def update_guild_settings(self, guild_id, notification_channel_id=None, public_notifications=None):
        updates = []
        params = [guild_id]
        
        if notification_channel_id is not None:
            updates.append("notification_channel_id = %s")
            params.append(notification_channel_id)
            
        if public_notifications is not None:
            updates.append("public_notifications = %s")
            params.append(public_notifications)
            
        if not updates:
            return False
            
        fields = []
        update_parts = []
        
        for update in updates:
            field = update.split(' = ')[0]
            fields.append(field)
            update_parts.append(f"{field} = new_data.{field}")
        
        query = f"""
        INSERT INTO guild_settings (guild_id, {', '.join(fields)})
        VALUES ({', '.join(['%s'] * (1 + len(fields)))}) AS new_data
        ON DUPLICATE KEY UPDATE {', '.join(update_parts)}
        """
        
        return await self.execute_query(query, params)
    
    
    async def setup_database(self):
        """Create all necessary database tables if they don't exist"""
        
        
        existing_tables = await self.execute_query(
            "SELECT TABLE_NAME FROM information_schema.tables WHERE TABLE_SCHEMA = %s",
            (self.db_config['database'],),
            fetch=True
        )
        
        
        existing_table_names = [table['TABLE_NAME'].lower() for table in existing_tables] if existing_tables else []
        
        
        tables_to_create = {
            "subscriptions": """
                CREATE TABLE subscriptions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    anime_id INT NOT NULL,
                    anime_title VARCHAR(255) NOT NULL,
                    date_subscribed DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_subscription (user_id, anime_id)
                )
            """,
            
            "notification_history": """
                CREATE TABLE notification_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    anime_id INT NOT NULL,
                    episode_number INT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    successful BOOLEAN DEFAULT TRUE,
                    UNIQUE KEY unique_notification (user_id, anime_id, episode_number)
                )
            """,
            
            "anime_cache": """
                CREATE TABLE anime_cache (
                    anime_id INT PRIMARY KEY,
                    title_romaji VARCHAR(255) NOT NULL,
                    title_english VARCHAR(255),
                    description TEXT,
                    cover_image_url VARCHAR(255),
                    status VARCHAR(50),
                    format VARCHAR(50),
                    episodes INT,
                    season VARCHAR(20),
                    season_year INT,
                    genres JSON,
                    site_url VARCHAR(255),
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """,
            
            "airing_schedule": """
                CREATE TABLE airing_schedule (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    anime_id INT NOT NULL,
                    episode INT NOT NULL,
                    airing_at BIGINT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_airing (anime_id, episode)
                )
            """,
            
            "user_settings": """
                CREATE TABLE user_settings (
                    user_id BIGINT PRIMARY KEY,
                    notification_enabled BOOLEAN DEFAULT TRUE,
                    preferred_title_format ENUM('romaji', 'english') DEFAULT 'romaji',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """,
            
            "guild_settings": """
                CREATE TABLE guild_settings (
                    guild_id BIGINT PRIMARY KEY,
                    notification_channel_id BIGINT,
                    public_notifications BOOLEAN DEFAULT FALSE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """
        }
        
        
        tables_created = 0
        for table_name, create_query in tables_to_create.items():
            if table_name not in existing_table_names:
                await self.execute_query(create_query)
                tables_created += 1
                print(f"✅ Created table: {table_name}")
        
        if tables_created == 0:
            print("✅ All database tables already exist")
        else:
            print(f"✅ Created {tables_created} new database tables")


def create_database():
    """Create the anime_bot database and tables"""
    load_dotenv()
    
    
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER', 'animebot'),
        'password': os.getenv('DB_PASSWORD', ''),
        'raise_on_warnings': True
    }
    
    
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    
    try:
        
        db_name = os.getenv('DB_NAME', 'anime_bot')
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        print(f"✅ Database '{db_name}' created or already exists")
        
        
        cursor.execute(f"USE {db_name}")
        
        
        tables = [
            
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                anime_id INT NOT NULL,
                anime_title VARCHAR(255) NOT NULL,
                date_subscribed DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_subscription (user_id, anime_id)
            )
            """,
            
            
            """
            CREATE TABLE IF NOT EXISTS notification_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                anime_id INT NOT NULL,
                episode_number INT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                successful BOOLEAN DEFAULT TRUE,
                UNIQUE KEY unique_notification (user_id, anime_id, episode_number)
            )
            """,
            
            
            """
            CREATE TABLE IF NOT EXISTS anime_cache (
                anime_id INT PRIMARY KEY,
                title_romaji VARCHAR(255) NOT NULL,
                title_english VARCHAR(255),
                description TEXT,
                cover_image_url VARCHAR(255),
                status VARCHAR(50),
                format VARCHAR(50),
                episodes INT,
                season VARCHAR(20),
                season_year INT,
                genres JSON,
                site_url VARCHAR(255),
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            
            """
            CREATE TABLE IF NOT EXISTS airing_schedule (
                id INT AUTO_INCREMENT PRIMARY KEY,
                anime_id INT NOT NULL,
                episode INT NOT NULL,
                airing_at BIGINT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_airing (anime_id, episode)
            )
            """,
            
            
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id BIGINT PRIMARY KEY,
                notification_enabled BOOLEAN DEFAULT TRUE,
                preferred_title_format ENUM('romaji', 'english') DEFAULT 'romaji',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """,
            
            
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                notification_channel_id BIGINT,
                public_notifications BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
        ]
        
        
        for table_query in tables:
            cursor.execute(table_query)
            
        print("✅ All tables have been created successfully")
        
    except mysql.connector.Error as err:
        print(f"❌ Error: {err}")
    finally:
        cursor.close()
        conn.close()


def main():
    
    print("Starting database setup...")
    create_database()
    print("Database setup complete!")
    
if __name__ == "__main__":
    main()