def register_commands(cls, console_manager):
    for attr_name in dir(cls):
        method = getattr(cls, attr_name)
        if callable(method) and hasattr(method, "command_info"):
            info = method.command_info

            flag_aliases = {}
            flag_descriptions = {}

            for param, (aliases, desc) in info.get("flags", {}).items():
                flag_descriptions[param] = desc
                for alias in aliases:
                    flag_aliases[alias] = param

            console_manager.register_command(
                action=method,
                aliases=info["aliases"],
                description=info["description"],
                usage=info["usage"],
                flag_aliases=flag_aliases,
                flag_descriptions=flag_descriptions
            )

def command(*, aliases, description="", usage="", flags=None):
    flags = flags or {}

    def decorator(func):
        func.command_info = {
            "aliases": aliases,
            "description": description,
            "usage": usage,
            "flags": flags,
        }

        return func
    return decorator
