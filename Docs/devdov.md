# SilkC Core Design Document

## Project Name
**SilkC** – the modular core framework for Python, inspired by Bukkit/Spigot plugin architecture.

Optional plugin naming: SilkAuth, SilkBilling, SilkPolice, SilkTaxi, SilkLoyalty, etc.

---

## Purpose / Vision
- Modular, standalone plugin framework for Python applications.
- Core provides infrastructure; all business logic lives in plugins.
- Inspired by Bukkit/Spigot:
  - Core handles environment, plugin loading, events, commands, and permissions.
  - Plugins are fully self-contained.
- Targets hobbyists, RP servers, simulations, or internal modular systems.

---

## Target Audience
- **Primary:** Python developers or hobbyists needing modular backends for RP, small games, or simulations.
- **Secondary:** Educators, hobbyist programmers, or teams creating plugin-based automation systems.
- **Tertiary:** Any developer seeking a professional, modular Python framework.

---

## Core Features
1. **Plugin System**
   - Load/unload plugins dynamically (.module or zip files)
   - Hotload/reload support
   - Hard & soft dependency management

2. **Event/Hook System**
   - Generic, domain-agnostic
   - Plugins define and fire events
   - Safe firing even if no listeners exist

3. **Command/API Registration**
   - Plugins can register commands and API routes
   - Conflict detection and warnings
   - Admins can select active commands/routes

4. **Permission System**
   - Plugins define permission nodes
   - Core manages roles & user assignments
   - Enforcement optional via plugin logic

5. **Environment & DB Management**
   - .env and config.yaml support
   - DB abstraction layer
   - Safe core API access for plugins

6. **Plugin Communication**
   - Optional plugin-to-plugin interactions
   - Soft/hard dependencies declared in manifests
   - Messaging system or API for inter-plugin calls

7. **Professional Packaging**
   - Single-file .module plugins
   - Manifest + optional digital signing
   - Warnings for unsigned plugins or missing dependencies

---

## Plugin Manifest Example
```yaml
name: Taxi
version: 1.0.0
description: Taxi meter system
dependencies:
  hard:
    - Police >=1.0.0
  soft:
    - Loyalty >=1.0.0
permissions:
  taxi.start: Allows starting a taxi ride
  taxi.admin: Admin taxi controls
```
## Core Manifest Example
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

---

## Design Philosophy
- Core is **domain-agnostic**; plugins encapsulate logic.
- Fail gracefully: missing dependencies or conflicts produce warnings, not crashes.
- Professional packaging and modularity for user experience and community growth.

---

## Areas for Enhancement
1. **Security Architecture**
   - Input validation at plugin boundaries
   - Permission sandboxing
   - Resource limiting (CPU/memory)
   - API access controls

2. **Plugin Lifecycle & Hotloading**
   - Manage persistent data on reload
   - Clean shutdown of active event listeners
   - Dependent plugin reload handling

3. **Event System**
   - Event priority levels (LOWEST → MONITOR)
   - Event cancellation
   - Async event handling

4. **Plugin Communication**
   - Formal service registry
   - Message passing for loose coupling
   - Controlled shared data stores

5. **Modern Python Standards**
   - Use pyproject.toml for manifests
   - setuptools entry points for plugin discovery
   - Dependency resolution via pip-tools or Poetry
   - Hierarchical configuration support

6. **Documentation & Community**
   - Developer guides, templates, best practices
   - Security guidelines for plugin devs
   - Community plugin repository with metrics

7. **Long-term Strategy**
   - Observability: plugin performance, resource usage, errors
   - API versioning & backward compatibility
   - Plugin health scoring (updates, security, performance, compatibility)

---

## MVP Scope (MVP+)
- Plugin loader with dependency handling (hard + soft)
- Generic event/hook system
- Command registration with conflict detection
- Permission API skeleton
- Single-file .module plugin support
- Digital signing verification

---

## Branding / Ecosystem Naming
- **Core:** SilkC (with its modules CoreA - CoreZ)
- **Plugins:** SilkAuth, SilkBilling, SilkPolice, SilkTaxi, SilkLoyalty
- **Plugin Ecosystem:** SilkModules / SilkPlugins
- **API:** SilkAPI

---
