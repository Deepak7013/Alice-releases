class MemoryPolicy:
    """Memory is advisory context, never authority."""
    sensitive_kinds = set()

    def can_influence(self, item):
        return item.confidence >= 0.5 and item.is_active()

    def can_grant_permission(self, item):
        return False

    def can_execute(self, item):
        return False
