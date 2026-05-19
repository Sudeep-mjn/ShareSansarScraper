BOT_NAME = 'sharesansar_scraper'

SPIDER_MODULES = ['sharesansar_scraper.spiders']
NEWSPIDER_MODULE = 'sharesansar_scraper.spiders'

# Obey robots.txt
ROBOTSTXT_OBEY = True

# Configure download delay
DOWNLOAD_DELAY = 3
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS_PER_DOMAIN = 1

# Enable cookies
COOKIES_ENABLED = True

# Telnet console
TELNETCONSOLE_ENABLED = False

# Logging
LOG_LEVEL = 'INFO'

# Export settings
FEED_EXPORT_ENCODING = 'utf-8'