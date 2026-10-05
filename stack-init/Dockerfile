# Built on the recyclarr image so stack-init can run a TRaSH sync itself
# before configuring Seerr (which needs the quality profiles to exist).
FROM ghcr.io/recyclarr/recyclarr:8
USER root
RUN apk add --no-cache python3 py3-requests py3-yaml
COPY stackinit /opt/stackinit/stackinit
ENV PYTHONPATH=/opt/stackinit PYTHONUNBUFFERED=1
ENTRYPOINT ["python3", "-m", "stackinit"]
CMD ["apply"]
