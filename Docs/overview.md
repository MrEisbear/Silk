# Silk Documentation (WIP)

# **I just noticed but the Core is INSANLY Work In Progress**
like srsly, this needs to be refactored completly, its only the 2nd day and its already a conjungled mess

## Meta
```yaml
meta =
{
    "id": "SilkE",
    "name": "Silk Example",
    "version": "1.0.0",
    "depends": {
        "hard": {"C": ">=0.2.0", "L": ">=0.2.0"},
        "soft": {"E": ">=0.2.0"}
    }
}
```

## StLib
The standard libary is the toolset of the Core consisting of: C-E-L-W-G

## Core Modules (A–Z)

### CoreA — Auth & Permission
Handles authentication and session management.  
Depends on: stlib
Provides:

### CoreC — Config
Central configuration handler for YAML.  
Depends on: stlib
Provides:

### CoreE — Errors
Defines global custom exceptions.  
Depends on: stlib
Provides:

### CoreG — Guard
Integrity and dependency checker.  
Depends on: stlib
Provides:

### CoreL — Logger
Colored log output with modes (DEBUG, VERBOSE, INFO and QUIET)
Depends on: stlib
Provides:

### CoreQ - QoL
Small helper functions
Depends on: stlib
Provides:

### CoreM - Event Manager

### CoreP - Plugin Manager

### CoreW - Werkzeug
Development tools and utilities (may also be referenced as part of the standard libary)
Depends on: stlib

### CoreU - Updater
