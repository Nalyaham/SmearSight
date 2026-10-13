from django.db import migrations


def seed(apps, schema_editor):
    Reader = apps.get_model("core", "Reader")
    if not Reader.objects.exists():
        for name, role in [("Lab technician", "technician"), ("Senior reader", "senior"), ("Laboratory lead", "lead")]:
            Reader.objects.create(name=name, role=role)


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
