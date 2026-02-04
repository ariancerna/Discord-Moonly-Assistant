import logging
from datetime import datetime
from pathlib import Path

class BotLogger:
    def __init__(self):
        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(exist_ok=True)
        
        # Bot logs (general, errors, startup)
        self.bot_log_file = self.logs_dir / "bot_logs.txt"
        
        # Command logs (user commands)
        self.command_log_file = self.logs_dir / "command_logs.txt"
        
        # Setup logging
        self.setup_logging()
    
    def setup_logging(self):
        """Setup logging configuration"""
        # Create formatter
        formatter = logging.Formatter(
            '[%(asctime)s] - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Bot logger
        self.bot_logger = logging.getLogger('bot')
        self.bot_logger.setLevel(logging.INFO)
        
        bot_handler = logging.FileHandler(self.bot_log_file, encoding='utf-8')
        bot_handler.setFormatter(formatter)
        self.bot_logger.addHandler(bot_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.bot_logger.addHandler(console_handler)
        
        # Command logger
        self.command_logger = logging.getLogger('commands')
        self.command_logger.setLevel(logging.INFO)
        
        command_handler = logging.FileHandler(self.command_log_file, encoding='utf-8')
        command_handler.setFormatter(formatter)
        self.command_logger.addHandler(command_handler)
    
    def log_command(self, user_name: str, user_id: int, command_name: str, options: str = ""):
        """Log command usage"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if options:
            log_message = f"Command Used | User: {user_name} (ID: {user_id}) | Command: /{command_name} | Options: {options}"
        else:
            log_message = f"Command Used | User: {user_name} (ID: {user_id}) | Command: /{command_name}"
        
        with open(self.command_log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] - {log_message}\n")
        
        print(f"[{timestamp}] - {log_message}")
    
    def info(self, message: str):
        """Log info message"""
        self.bot_logger.info(message)
    
    def error(self, message: str):
        """Log error message"""
        self.bot_logger.error(message)
    
    def warning(self, message: str):
        """Log warning message"""
        self.bot_logger.warning(message)
    
    def debug(self, message: str):
        """Log debug message"""
        self.bot_logger.debug(message)

# Global logger instance
logger = BotLogger()