from pathlib import Path
import urllib.request,tarfile,io,subprocess,json
base=Path('/home/assistant/.onecli/refresh-fix');base.mkdir(exist_ok=True)
sha='fe0981f09122358d4b3c721ef3e141026a2fdc46'
archive=urllib.request.urlopen(f'https://api.github.com/repos/onecli/onecli/tarball/{sha}').read()
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
 archive_root=Path(tar.getnames()[0]).parts[0]
 import re
 if not re.fullmatch(r'onecli-onecli-[0-9a-f]{7,40}',archive_root):raise SystemExit('Unexpected archive root')
 source=base/archive_root
 if source.exists():
  import shutil
  shutil.rmtree(source)
 tar.extractall(base,filter='data')
p=source/'apps/gateway/src/secret_inject.rs';s=p.read_text()
old='''        .form(&[
            ("grant_type", "refresh_token"),'''
# Backport the upstream v2 OAuth fix into the current all-in-one gateway.
new='''        .form(&[
            ("client_id", "app_EMoamEEZ73f0CkXaXp7hrann"),
            ("grant_type", "refresh_token"),'''
if s.count(old)!=1:raise SystemExit('Unexpected pinned source; no patch applied')
p.write_text(s.replace(old,new))
(base/'source.json').write_text(json.dumps({'upstream':'onecli/onecli','tag':'v1.41.0','commit':sha,'patch':'Backport upstream OAuth refresh client_id parameter; no DB/schema changes'},indent=2))
(source/'Dockerfile.refresh-fix').write_text('''FROM rust:1-alpine@sha256:a96ea6d18d4062e38f16cfbadd8b4541d622f2527dd0a5eca1fb36d301da4e88 AS build
RUN apk add --no-cache musl-dev pkgconfig openssl-dev openssl-libs-static
WORKDIR /build
COPY apps/gateway/ ./
ENV CARGO_PROFILE_RELEASE_LTO=false CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16 CARGO_PROFILE_RELEASE_OPT_LEVEL=1
RUN cargo build --release --locked -j 2
FROM ghcr.io/onecli/onecli:1.41.0@sha256:66dc84042310cab762ed3b1f71a98349a72aa132ad44651b7ae76c371aaafe6b
COPY --from=build /build/target/release/onecli-gateway /usr/local/bin/onecli-gateway
''')
print('Building isolated backport against pinned upstream:',sha,flush=True)
subprocess.run(['docker','build','-f','Dockerfile.refresh-fix','-t','onecli:1.41.0-refresh-fix',str(source)],cwd=source,check=True)
