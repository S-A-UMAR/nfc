from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('websites', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='website',
            name='slug',
            field=models.SlugField(blank=True, max_length=150, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='website',
            name='show_hero',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='website',
            name='show_about',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='website',
            name='show_services',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='website',
            name='show_products',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='website',
            name='show_gallery',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='website',
            name='show_social',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='website',
            name='show_contact',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='website',
            name='show_footer',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='website',
            name='primary_color',
            field=models.CharField(default='#000000', max_length=20),
        ),
        migrations.AddField(
            model_name='website',
            name='secondary_color',
            field=models.CharField(default='#ffffff', max_length=20),
        ),
        migrations.AddField(
            model_name='website',
            name='button_style',
            field=models.CharField(choices=[('solid', 'Solid'), ('outline', 'Outline'), ('rounded', 'Rounded')], default='solid', max_length=20),
        ),
        migrations.AlterField(
            model_name='website',
            name='status',
            field=models.CharField(choices=[('draft', 'Draft / Designing'), ('published', 'Published & Live'), ('unpublished', 'Unpublished'), ('maintenance', 'Maintenance Mode')], default='draft', max_length=30),
        ),
        migrations.CreateModel(
            name='Service',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('description', models.TextField(blank=True)),
                ('price', models.CharField(blank=True, max_length=100)),
                ('image', models.ImageField(blank=True, null=True, upload_to='websites/services/')),
                ('is_active', models.BooleanField(default=True)),
                ('display_order', models.PositiveIntegerField(default=0)),
                ('website', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='services', to='websites.website')),
            ],
            options={
                'ordering': ['display_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('description', models.TextField(blank=True)),
                ('price', models.CharField(blank=True, max_length=100)),
                ('image', models.ImageField(blank=True, null=True, upload_to='websites/products/')),
                ('is_active', models.BooleanField(default=True)),
                ('display_order', models.PositiveIntegerField(default=0)),
                ('website', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='products', to='websites.website')),
            ],
            options={
                'ordering': ['display_order', 'id'],
            },
        ),
    ]
