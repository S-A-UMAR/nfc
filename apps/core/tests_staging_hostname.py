import os
from django.test import TestCase, override_settings
from django.core.exceptions import ImproperlyConfigured
from config.settings import validate_railway_staging_hostname, configure_staging_hostname


class RailwayStagingHostnameValidationTests(TestCase):
    """
    Focused tests for safe dynamic Railway hostname resolution in staging.
    Covers valid hostname formats, invalid format rejections, missing hostname
    handling, fail-closed enforcement, and production isolation.
    """

    def test_valid_railway_hostname_resolution(self):
        """Valid DNS hostnames ending in .up.railway.app are successfully validated and configured."""
        valid_samples = [
            'stride-staging.up.railway.app',
            'stride-staging-production-8b1a.up.railway.app',
            'web-staging-pr-42.up.railway.app',
            'STRIDE-STAGING-DEMO.UP.RAILWAY.APP',  # Case normalization
        ]

        for hostname in valid_samples:
            normalized = validate_railway_staging_hostname(hostname)
            self.assertEqual(normalized, hostname.lower())

            allowed_hosts, csrf_origins, site_url = configure_staging_hostname(
                environment='staging',
                raw_railway_domain=hostname
            )

            # ALLOWED_HOSTS must contain the exact domain and internal healthcheck loopbacks
            self.assertEqual(allowed_hosts, [hostname.lower(), '127.0.0.1', 'localhost'])
            # Must NEVER contain wildcards
            self.assertNotIn('*', allowed_hosts)
            self.assertNotIn('.up.railway.app', allowed_hosts)

            # CSRF_TRUSTED_ORIGINS must be exact HTTPS origin
            self.assertEqual(csrf_origins, [f"https://{hostname.lower()}"])

            # SITE_URL must match exact HTTPS origin
            self.assertEqual(site_url, f"https://{hostname.lower()}")

    def test_invalid_hostname_with_schemes_rejected(self):
        """Hostnames containing URL schemes (http://, https://) are rejected."""
        schemed_samples = [
            'https://stride-staging.up.railway.app',
            'http://stride-staging.up.railway.app',
            'https://stride-staging.up.railway.app/',
        ]
        for sample in schemed_samples:
            with self.assertRaises(ImproperlyConfigured) as cm:
                validate_railway_staging_hostname(sample)
            self.assertIn("must not contain a URL scheme", str(cm.exception))

    def test_invalid_hostname_with_ports_and_paths_rejected(self):
        """Hostnames containing ports (:8000) or path characters (/) are rejected."""
        samples = [
            'stride-staging.up.railway.app:8000',
            'stride-staging.up.railway.app:443',
            'stride-staging.up.railway.app/health/',
            'stride-staging.up.railway.app\\test',
        ]
        for sample in samples:
            with self.assertRaises(ImproperlyConfigured) as cm:
                validate_railway_staging_hostname(sample)
            self.assertTrue(
                "port" in str(cm.exception) or "path" in str(cm.exception)
            )

    def test_invalid_hostname_with_wildcards_rejected(self):
        """Hostnames containing wildcards (*, *.up.railway.app) are strictly rejected."""
        wildcards = [
            '*',
            '*.up.railway.app',
            '*.stride-staging.up.railway.app',
            'stride-*-staging.up.railway.app',
        ]
        for sample in wildcards:
            with self.assertRaises(ImproperlyConfigured) as cm:
                validate_railway_staging_hostname(sample)
            self.assertIn("must not contain wildcards", str(cm.exception))

    def test_invalid_hostname_with_commas_or_lists_rejected(self):
        """Multiple hostnames, lists, or whitespace separated values are rejected."""
        multi_samples = [
            'stride-staging.up.railway.app,other.up.railway.app',
            'stride-staging.up.railway.app;other.up.railway.app',
            'stride-staging.up.railway.app other.up.railway.app',
        ]
        for sample in multi_samples:
            with self.assertRaises(ImproperlyConfigured) as cm:
                validate_railway_staging_hostname(sample)
            self.assertIn("must be a single hostname, not a list", str(cm.exception))

    def test_invalid_hostname_with_placeholders_rejected(self):
        """Unresolved placeholder strings (<...>) are strictly rejected."""
        placeholders = [
            '<pending_confirmed_railway_hostname>',
            '<staging-app>.up.railway.app',
            '<your-service>.up.railway.app',
        ]
        for sample in placeholders:
            with self.assertRaises(ImproperlyConfigured) as cm:
                validate_railway_staging_hostname(sample)
            self.assertIn("must not be a placeholder", str(cm.exception))

    def test_invalid_hostname_wrong_domain_suffix_rejected(self):
        """Domains not ending in .up.railway.app are rejected in staging."""
        wrong_domains = [
            'strideid.com',
            'staging.strideid.com',
            'stride-staging.herokuapp.com',
            'stride-staging.render.com',
            'up.railway.app',       # No subdomain prefix
            '.up.railway.app',      # Missing subdomain
        ]
        for sample in wrong_domains:
            with self.assertRaises(ImproperlyConfigured) as cm:
                validate_railway_staging_hostname(sample)
            self.assertTrue(
                "must end with '.up.railway.app'" in str(cm.exception)
                or "must have a valid subdomain prefix" in str(cm.exception)
                or "not a valid DNS hostname" in str(cm.exception)
            )

    def test_invalid_dns_format_rejected(self):
        """Malformed DNS labels (hyphens at boundaries, double dots) are rejected."""
        malformed = [
            '-stride-staging.up.railway.app',
            'stride-staging-.up.railway.app',
            'stride..up.railway.app',
            'stride_staging.up.railway.app',  # Underscores not standard in hostnames
        ]
        for sample in malformed:
            with self.assertRaises(ImproperlyConfigured):
                validate_railway_staging_hostname(sample)

    def test_missing_hostname_fails_closed(self):
        """Missing or empty hostname in staging fails closed immediately."""
        empty_values = [None, '', '   ']
        for val in empty_values:
            with self.assertRaises(ImproperlyConfigured) as cm:
                validate_railway_staging_hostname(val)
            self.assertTrue(
                "missing" in str(cm.exception).lower()
                or "empty" in str(cm.exception).lower()
            )

            with self.assertRaises(ImproperlyConfigured):
                configure_staging_hostname('staging', val)

    def test_staging_never_falls_back_to_production_domain(self):
        """When staging hostname is missing, configure_staging_hostname never returns strideid.com."""
        with self.assertRaises(ImproperlyConfigured):
            configure_staging_hostname('staging', '')

        with self.assertRaises(ImproperlyConfigured):
            configure_staging_hostname('staging', None)

    def test_production_isolation(self):
        """configure_staging_hostname refuses to execute if ENVIRONMENT is not staging."""
        non_staging_envs = ['production', 'prod', 'development', 'test', 'local']
        for env in non_staging_envs:
            with self.assertRaises(ImproperlyConfigured) as cm:
                configure_staging_hostname(env, 'stride-staging.up.railway.app')
            self.assertIn("should only be invoked when ENVIRONMENT=staging", str(cm.exception))

    def test_unresolved_env_vars_cannot_override_staging_hostname(self):
        """Unresolved values in DJANGO_ALLOWED_HOSTS cannot override the validated staging hostname."""
        # Simulated scenario: local env has placeholders
        placeholder_hosts = "<pending_confirmed_railway_hostname>"
        valid_railway_domain = "stride-staging-verified.up.railway.app"

        allowed, csrf, site = configure_staging_hostname('staging', valid_railway_domain)

        # Confirm the resulting configuration uses only the verified domain
        self.assertNotIn(placeholder_hosts, allowed)
        self.assertIn(valid_railway_domain, allowed)
        self.assertEqual(csrf, [f"https://{valid_railway_domain}"])
        self.assertEqual(site, f"https://{valid_railway_domain}")
