// 프로톤 드라이브 공개 링크 받기 — 프로톤이 공개한 드라이브 SDK·암호 라이브러리를 묶어 app/proton.js로 만듦 (npm run build).
// 브라우저에서 풀고, 프로톤 API 요청은 봇카이브 서버(/api/proton)가 대신 보냄 (프로톤 API는 다른 사이트에서 바로 못 부름).
// 로그인 없는 공개 링크만 씀. 프로톤 SDK 규칙대로 앱 이름을 x-pm-appversion에 정직하게 밝힘.
import 'core-js/proposals/array-buffer-base64';
import { ProtonDriveClient, MemoryCache, OpenPGPCryptoWithCryptoProxy } from '@protontech/drive-sdk';
import { CryptoProxy } from '@protontech/crypto';
import { Api } from '@protontech/crypto/proxy/endpoint/api.ts';
import { getSrp, computeKeyPassword, generateKeySalt } from '@protontech/crypto/srp';

const APP_VERSION = 'external-drive-botkive@1.0.0-stable';
let ready = false;

function makeClient(relay) {
  if (!ready) { Api.init({}); CryptoProxy.setEndpoint(new Api()); ready = true; }
  const no = async () => { throw new Error('공개 링크만 받을 수 있어요'); };
  const http = req => relay(req, APP_VERSION);
  const quiet = {debug() {}, info() {}, warn(t) { console.warn('[프로톤]', t); }, error(t, e) { console.warn('[프로톤]', t, e); }};
  return new ProtonDriveClient({
    telemetry: {getLogger: () => quiet, recordMetric: () => {}},
    httpClient: {fetchJson: http, fetchBlob: http},
    entitiesCache: new MemoryCache(),
    cryptoCache: new MemoryCache(),
    account: {getOwnPrimaryAddress: no, getOwnAddress: no, getOwnAddresses: async () => [], hasProtonAccount: async () => false, getPublicKeys: async () => []},
    openPGPCryptoModule: new OpenPGPCryptoWithCryptoProxy(CryptoProxy),
    srpModule: {
      getSrp: (Version, Modulus, ServerEphemeral, Salt, password) => getSrp({Version, Modulus, ServerEphemeral, Salt}, {password}),
      computeKeyPassword, generateKeySalt, getSrpVerifier: no,
    },
  });
}

// 링크를 열어 파일 목록 → [{name, path, size, get(onProg) → File}] (폴더면 하위 폴더 3단계·파일 300개까지)
async function open(url, password, relay) {
  const c = makeClient(relay);
  const info = await c.experimental.getURLAccessInfo(url);
  if (info.isCustomPasswordProtected && !password) {
    const e = new Error('암호가 걸린 링크예요');
    e.needPassword = true;
    throw e;
  }
  const pub = await c.experimental.authURLAccess(url, password || undefined, true);
  const out = [];
  const nameOf = n => (n.name && n.name.ok ? n.name.value : '') || 'file';
  const walk = async (node, path, depth) => {
    if (node.type === 'file') {
      const name = nameOf(node);
      out.push({name, path: path + name, size: node.activeRevision && node.activeRevision.claimedSize || 0, get: onProg => fetchFile(pub, node.uid, name, onProg)});
      return;
    }
    if (node.type !== 'folder' || depth > 3) return;
    for await (const ch of pub.iterateFolderChildren(node.uid)) {
      if (out.length >= 300) break;
      await walk(ch, depth ? path + nameOf(node) + '/' : path, depth + 1);
    }
  };
  await walk(await pub.getRootNode(), '', 0);
  return out;
}

async function fetchFile(pub, uid, name, onProg) {
  const dl = await pub.getFileDownloader(uid);
  const size = dl.getClaimedSizeInBytes ? dl.getClaimedSizeInBytes() : 0;
  const parts = [];
  const ctl = dl.downloadToStream(new WritableStream({write(chunk) { parts.push(chunk); }}), n => onProg && onProg(n, size || 0));
  await ctl.completion();
  return new File(parts, name);
}

window.BKProton = {open};
