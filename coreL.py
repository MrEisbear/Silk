meta = {
    "id": "coreL",
    "name": "Silk Logger",
    "version": "1.0.0",
    "depends": {
        "hard": {},
        "soft": {}
    }
}

class Logger:
    def __init__(self, name):
        self.name = name
        self.module = False
        try:
            from colorama import Fore, Style, just_fix_windows_console
            just_fix_windows_console()
            self.module = True
            self.Fore = Fore
            self.Style = Style
        except ModuleNotFoundError:
            print(f"[ERROR] [Logger] Colorama module not found!")
            print(f"[INFO] [Logger] Fallback to ANSI Codes (Does not work on Windows!)")
            self.module = False

        self.reset() # Resets the terminal colours to ensure everything is in correct colour

    def version(self):
        return meta["version"]

    def reset(self):
        if self.module:
            print(self.Fore.RESET + self.Style.RESET_ALL, end="")
        else:
            print("\033[0m", end="")

    def info(self, message, module_name=None):
        name = module_name or self.name
        print(f"[INFO] [{name}] {message}")

    def warning(self, message, module_name=None):
        name = module_name or self.name
        if self.module:
            print(self.Fore.YELLOW + f"[WARNING] [{name}] {message}" + self.Style.RESET_ALL)
        else:
            print(f"\033[33m[WARNING] [{name}] {message}\033[0m")

    def error(self, message, module_name=None):
        name = module_name or self.name
        if self.module:
            print(self.Fore.RED + f"[ERROR] [{name}] {message}" + self.Style.RESET_ALL)
        else:
            print(f"\033[31m[ERROR] [{name}] {message}\033[0m")

    def debug(self, message, module_name=None):
        name = module_name or self.name
        if self.module:
            print(self.Fore.BLUE + f"[DEBUG] [{name}] {message}" + self.Style.RESET_ALL)
        else:    
            print(f"\033[34m[DEBUG] [{name}] {message}\033[0m")

    def verbose(self, message, module_name=None):
        name = module_name or self.name
        if self.module:
            print(self.Fore.MAGENTA + f"[VERBOSE] [{name}] {message}" + self.Style.RESET_ALL)
        else:
            print(f"\033[35m[VERBOSE] [{name}] {message}\033[0m")

    def fatal(self, message, module_name=None):
        name = module_name or self.name
        if self.module:
            print(self.Fore.RED + self.Style.BRIGHT + f"[FATAL] [{name}] {message}" + self.Style.RESET_ALL)
        else:
            print(f"\033[1;31m[FATAL] [{name}] {message}\033[0m")

    def set_mode(self, mode):
        mode = mode.upper()
        match mode:
            case "DEBUG":
                self.verbose = lambda message, module_name=None: None
                self.mode = "DEBUG"
            case "QUIET": # deactivates everything except error and fatal
                self.info = lambda message, module_name=None: None
                self.warning = lambda message, module_name=None: None
                self.debug = lambda message, module_name=None: None
                self.verbose = lambda message, module_name=None: None
                self.mode = "QUIET"
            case "VERBOSE":
                self.mode = "VERBOSE" # dont deactivate anything as it shows everything
            case _: # aka INFO / default:
                self.debug = lambda message, module_name=None: None
                self.verbose = lambda message, module_name=None: None
                self.mode = "INFO"

    def get_child(self, name):
        # Returns a new Logger wrapper that keeps the same formatting but uses a different module name
        parent = self
        class ChildLogger:
            def __init__(self, module_name):
                self.name = module_name
            def info(self, msg): parent.info(self.name, msg)
            def warning(self, msg): parent.warning(self.name, msg)
            def error(self, msg): parent.error(self.name, msg)
            def debug(self, msg): parent.debug(self.name, msg)
            def verbose(self, msg): parent.verbose(self.name, msg)
            def fatal(self, msg): parent.fatal(self.name, msg)
        return ChildLogger(name)


def init(context):
    # Put Logger instance into context so other modules can use it
    context["logger"] = Logger("CoreL")
    context["logger"].info(f"{meta['name']} loaded successfully!")