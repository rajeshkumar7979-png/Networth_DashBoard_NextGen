def pack_prompt_extras(pack):
    lines = [
        AI_QUESTION,
        "",
        "Deterministic flags already computed (do not invent new ones):",
    ]
    groups = (
        (pack.green, "GREEN"),
        (pack.red, "RED"),
        (pack.watch, "WATCH"),
        (pack.gaps, "GAPS"),
    )
    for group, title in groups:
        if not group:
            continue
        lines.append(title + ":")
        for flag in group:
            lines.append("- [%s] %s: %s" % (flag.source, flag.label, flag.text))
    if getattr(pack, "parameters", None):
        lines.append("Verified parameters (restate, do not recompute):")
        for item in list(pack.parameters)[:24]:
            lines.append("- %s: %s %s (%s)" % (
                item.get("Parameter"),
                item.get("Value"),
                item.get("Unit") or "",
                item.get("Source") or "observed",
            ))
    if pack.freshness:
        lines.append("Freshness: " + " | ".join(pack.freshness))
    return "\n".join(lines)
