from django.db import models
from accounts.models import CustomUser


class Notification(models.Model):
    TYPE_CHOICES = (
        ("danger", "Danger"),  # 🔴 Critical - low stock, stock out
        ("warning", "Warning"),  # 🟡 Warning - credit limit, reorder
        ("success", "Success"),  # 🟢 Positive - sales increase
        ("info", "Info"),  # 🔵 Information - demand requests
        ("ai", "AI Insight"),  # 🤖 AI recommendations
    )

    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default="info"
    )
    is_read = models.BooleanField(default=False)
    action_url = models.CharField(max_length=200, blank=True, null=True)
    action_label = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_for = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.notification_type}] {self.title}"

    @property
    def dot_color(self):
        colors = {
            "danger": "#EF4444",
            "warning": "#F59E0B",
            "success": "#10B981",
            "info": "#2563EB",
            "ai": "#7C3AED",
        }
        return colors.get(self.notification_type, "#64748B")

    @property
    def icon(self):
        icons = {
            "danger": "bi-exclamation-circle-fill",
            "warning": "bi-exclamation-triangle-fill",
            "success": "bi-graph-up-arrow",
            "info": "bi-info-circle-fill",
            "ai": "bi-robot",
        }
        return icons.get(self.notification_type, "bi-bell-fill")
