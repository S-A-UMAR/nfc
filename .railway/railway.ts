import { defineRailway, project, service } from "railway/iac";

export default defineRailway(() => {
  const web = service("stride", {
    build: {
      builder: "NIXPACKS",
      buildCommand: "python -m pip install -r requirements.txt && python manage.py collectstatic --noinput",
    },
    start: "gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120",
    healthcheck: "/health/",
    deploy: {
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 10,
    },
  });

  return project("stride", {
    resources: [web],
  });
});
