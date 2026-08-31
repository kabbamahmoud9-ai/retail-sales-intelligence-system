from django.db import migrations


def set_admin_role(apps, schema_editor):
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.filter(is_superuser=True).exclude(role='admin').update(role='admin')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_customuser_profile_picture'),
    ]

    operations = [
        migrations.RunPython(set_admin_role, noop_reverse),
    ]
