version = 0.1

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
        return version

    def reset(self):
        if self.module:
            print(self.Fore.RESET + self.Style.RESET_ALL, end="")
        else:
            print("\033[0m", end="")

    def info(self, message):
        print(f"[INFO] [{self.name}] {message}")

    def warning(self, message):
        if self.module:
            print(self.Fore.YELLOW + f"[WARNING] [{self.name}] {message}" + self.Style.RESET_ALL)
        else:
            print(f"\033[33m[WARNING] [{self.name}] {message}\033[0m")

    def error(self, message):
        if self.module:
            print(self.Fore.RED + f"[ERROR] [{self.name}] {message}" + self.Style.RESET_ALL)
        else:
            print(f"\033[31m[ERROR] [{self.name}] {message}\033[0m")

    def debug(self, message):
        if self.module:
            print(self.Fore.BLUE + f"[DEBUG] [{self.name}] {message}" + self.Style.RESET_ALL)
        else:    
            print(f"\033[34m[DEBUG] [{self.name}] {message}\033[0m")

    def verbose(self, message):
        if self.module:
            print(self.Fore.MAGENTA + f"[VERBOSE] [{self.name}] {message}" + self.Style.RESET_ALL)
        else:
            print(f"\033[35m[VERBOSE] [{self.name}] {message}\033[0m")

    def fatal(self, message):
        if self.module:
            print(self.Fore.RED + self.Style.BRIGHT + f"[FATAL] [{self.name}] {message}" + self.Style.RESET_ALL)
        else:
            print(f"\033[1;31m[FATAL] [{self.name}] {message}\033[0m")

    def set_mode(self, mode):
        mode = mode.upper()
        match mode:
            case "DEBUG":
                self.verbose = lambda message: None
                self.mode = "DEBUG"
            case "QUIET": # deactivates everything except error and fatal
                self.info = lambda message: None
                self.warning = lambda message: None
                self.debug = lambda message: None
                self.verbose = lambda message: None
                self.mode = "QUIET"
            case "VERBOSE":
                self.mode = "VERBOSE" # dont deactivate anything as it shows everything
            case _: # aka INFO / default:
                self.debug = lambda message: None
                self.verbose = lambda message: None
                self.mode = "INFO"

