FROM python:3.12-slim

LABEL org.opencontainers.image.title="Site Health Checker" \
      org.opencontainers.image.description="Audit any website for accessibility (WCAG) problems, broken links, slow pages, redirect chains and missing titles." \
      org.opencontainers.image.source="https://github.com/Reenakotadiya/site-health-checker" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.authors="Reena Kotadiya"

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY site_health_checker ./site_health_checker
RUN pip install --no-cache-dir . && rm -rf /src

# Reports are written here; mount a folder to keep them: -v "$PWD:/reports"
WORKDIR /reports
ENTRYPOINT ["site-health-checker"]
CMD ["--help"]
