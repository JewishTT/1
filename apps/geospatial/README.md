# Geospatial context workspace

God's Eye View is mounted as an optional, separately built spatial workspace.
The upstream project is pinned as a Git submodule at a reviewed commit; its
application runtime is not imported into the Cognitive control plane.

## Initialize and run

```bash
git submodule update --init --recursive apps/geospatial/gods-eye-view
docker compose -f apps/deploy/docker-compose.yml \
  -f apps/deploy/compose.geospatial.yml --profile geospatial up -d gods-eye-view
```

For Vite development, set this in the webapp's local environment:

```dotenv
VITE_GEV_EMBED_URL=http://127.0.0.1:14173
```

The upstream document is served in embed mode. Its Content-Security-Policy
must explicitly allow the webapp origin through GEV_EMBED_FRAME_ANCESTORS.
The geospatial compose overlay defaults to loopback-only development origins.
For production, replace that value with the exact HTTPS webapp origin and
publish the service only through an authenticated reverse proxy on a private
network.

The optional service is not part of the core profile. It receives no person,
research-case or entity identifiers, queries or evidence. The view is limited
to public environmental events, infrastructure and space context.

## Boundaries and licensing

- No named-person search, person tracking, face recognition, camera/ALPR
  collection, voice collection or pivots from person records into live cameras.
- This is exploratory context, not a safety-critical or authoritative source.
- The upstream MIT license covers upstream source code only. Live and bundled
  data remain subject to individual providers' terms and licenses. Preserve
  attribution and non-commercial restrictions; do not copy upstream datasets
  into Cognitive storage by default.
- Default operation is keyless and loopback-only. Never put provider
  credentials in the web bundle or a public deployment.
- The iframe uses a sandbox, no referrer, and grants no camera, microphone or
  geolocation permissions.
