# AI-Reverse-Engineer: App Reverse Engineering with Just 8GB VRAM

[![Russian Version](https://img.shields.io/badge/Language-Русский-blue.svg)](README_RU.md)
[![Promo Posts](https://img.shields.io/badge/Promo%20Posts-RU%20%2F%20EN-purple.svg)](PROMO.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Hardware: 8GB VRAM](https://img.shields.io/badge/Hardware-8GB%20VRAM%20Compatible-orange.svg)](https://www.nvidia.com)

A battle-tested blueprint for auditing, decompiling, and clean-room re-architecting complex mobile applications using a standard **8GB VRAM consumer GPU** (RTX 3060 / 4060 / 5060) combined with zero-token static triage and multi-tier agent routing ([cli-subagent](https://github.com/pacodelavega/cli-subagent)).

---

## The Problem: The Cloud-Token & Context Trap

Modern enterprise mobile apps package tens of megabytes of compiled Dalvik bytecode (`classes.dex`), thousands of obfuscated classes, and 100,000+ string pool identifiers. 

- **Naive Approach:** Dumping decompiled Smali or entire Java sources into frontier cloud models (Claude 3.5 Sonnet, GPT-4o, Codex) immediately exhausts context windows, triggers rate-limits (`429`), costs substantial API credits, and risks moralizing refusals on defensive security and reverse-engineering queries.
- **Pure Local Approach:** Running heavy 70B+ frontier models locally requires 48GB–80GB+ VRAM (multi-GPU workstations or enterprise clusters), completely out of reach for a regular developer laptop or standard 8GB desktop card.

### The 8GB VRAM Solution: Hybrid Tiering

```
┌────────────────────────────────────────────────────────────────────────┐
│                      Target Application (APK/DEX)                      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Tier 0: Zero-Token Binary Parsing (Python / Regex / DEX Table Walk)   │
│  - Extracts DEX string pools, Retrofit annotations, Moshi JSON options │
│  - 100,000+ raw strings reduced to ~30 domain symbols in < 500 ms      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Tier 1: Local 8GB VRAM Agent (Qwen 2.5 / 3.5 9B Q4_K_M / Q8_0)        │
│  - Engine: LM Studio / vLLM / Ollama (OpenAI-compatible /v1)           │
│  - Uncensored security evaluation, AST decompilation, log compression   │
│  - Produces strict, minimal DTO models without burning cloud tokens    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  Tier 2: Multi-Agent Subagent Router (/cli-subagent)                   │
│  - Dynamic pool balancing, circuit-breakers, zero-downtime failover    │
│  - Feeds pristine 2 KB schemas into Workhorse / Frontier Architects    │
│    (Codex 6.1 Sol / Claude Opus / Gemini Flash) for clean synthesis    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Real-World Case Study: Deconstructing a Monopolist Intercom App

In this reference case study, residents were locked out of their own residential entrance doors when running system VPNs and suffered frequent app crashes instead of receiving an emergency unlock code, despite paying mandatory monthly utility fees for unwanted "smart" intercom hardware.

### 1. Dual-Circuit VPN & Proxy Blocking
- **Client-Side Trigger:** Located in `AppAppAccessManagerImpl.kt` (`VpnAccessChecker`):
  - Calls [`NetworkCapabilities.hasTransport(TRANSPORT_VPN)`](https://developer.android.com/reference/android/net/NetworkCapabilities#TRANSPORT_VPN).
  - Iterates [`LinkProperties.getInterfaceName()`](https://developer.android.com/reference/android/net/LinkProperties#getInterfaceName()) probing for virtual interface names (`tun0`, `ppp0`, `p2p0`).
  - Instantiates `AppAccessDeniedReason$Vpn` and forces `NoAppAccessViewModel` to lock the UI with `show_blockingscreennet_vpn`.
- **Server-Side WAF Filter:** Requests hitting cloud endpoints (`keyapis.key.rt.ru`, `vc.key.rt.ru`) inspect client IP geolocation and hosting ASNs, returning `HTTP 477` on foreign VPN routes.

### 2. The Door Opening Failure & The Emergency Code Bug
- **100% Cloud-First Actuation:** Door unlocking relies strictly on `OpenDoorInteractor` calling `POST v2/app/devices/{id}/open` over real-time REST and SIP gateways ([pjsip / SipService](https://github.com/gotev/android-sipservice)).
- **The Fatal Fallback Glitch:** Emergency unlock codes are downloaded by `UpdateEmergencyCodesUseCase` into `PersistentStorage`. However, when door unlocking fails due to a network drop or WAF block, the error-handling lambda (`Lqg5`) attempts to call `GetDeviceInteractor(deviceId)` **over the network again**. When the network is broken, the second call throws an unhandled exception (`Lkg5`), crashing the flow before the local storage is ever queried.

### 3. Monetization & Ad Bloat
- Hardcoded banner modules (`BannersRepositoryImpl`, `CanShowNasledieBannerUseCase`, `CanShowDomaAiUseCase`).
- Telemetry trackers: [Yandex Metrica](https://appmetrica.yandex.com/), [Google Mobile Ads](https://developers.google.com/admob/android/quick-start), Sentry.
- Paywall notifications upon expiration of trial periods (`Banner$SubscriptionEndedAfterPromoPeriodBanner`).

---

## Practical Guide: Reverse Engineering with 8GB VRAM

### Step 1: Zero-Token String & Symbol Extraction
Never decompile an entire APK into millions of Smali lines if you only need the domain logic. A 20-line Python script can read the DEX String ID table directly in `< 100 ms`:

```python
import struct, glob

def get_dex_strings(dex_path):
    strings = []
    with open(dex_path, 'rb') as f:
        data = f.read()
    string_ids_size, string_ids_off = struct.unpack('<II', data[56:64])
    for i in range(string_ids_size):
        off = struct.unpack('<I', data[string_ids_off + i*4 : string_ids_off + (i+1)*4])[0]
        # Read ULEB128 string length
        length, shift, idx = 0, 0, off
        while True:
            b = data[idx]; idx += 1; length |= (b & 0x7f) << shift
            if (b & 0x80) == 0: break
            shift += 7
        strings.append(data[idx:idx+length].decode('utf-8', errors='ignore'))
    return strings
```

### Step 2: Recovering Exact JSON Schemas from Moshi Adapters
Modern Android apps using [Square Moshi](https://github.com/square/moshi) compile JSON field definitions into `JsonReader.Options.of(...)` inside generated `*JsonAdapter.kt` classes. You can parse these bytecode constants to recover 100% of the original field names without access to source code.

### Step 3: Local 8GB Model Configuration
Set up a fast, uncensored 9B parameter model locally via [LM Studio](https://lmstudio.ai/) or [vLLM](https://github.com/vllm-project/vllm):
- **Model Recommendation:** `Qwen2.5-Coder-7B-Instruct`, `Qwen/Qwen2.5-7B-Instruct`, or `qwen3.5-9b-uncensored` (GGUF Q4_K_M or Q8_0).
- **VRAM Budget:**
  - Model weights: ~5.5 GB
  - KV-cache (8K-16K context with FP8/Q8 quantization): ~1.8 GB
  - Total allocation: **< 7.5 GB VRAM** (fits cleanly on RTX 3060 8GB / RTX 4060 8GB / RTX 5060 8GB).
- **Role:** Feed raw string dumps and bytecode snippets to the local model. Instruct it to compress the findings into clean Kotlin DTOs and API interfaces.

### Step 4: Multi-Agent Orchestration via `/cli-subagent`
Use the [cli-subagent](https://github.com/pacodelavega/cli-subagent) protocol to route tasks across local and remote engines:

```bash
# Extract & compress schemas via local 8GB model
python scripts/cli.py --provider custom --model qwen3.5-9b --tier fast -p "Compress Moshi schemas to Kotlin DTO" --run

# Dispatch synthesized schemas to Frontier Architect (Codex 6.1 Sol / Claude Sonnet)
python scripts/cli.py --provider codex --model gpt-6.1-sol --effort xhigh -p "Synthesize clean-client network core" --run
```

---

## Clean-Room Solution Architecture

The clean-room client (`clean-client/`) replaces the broken vendor app with an offline-first, resilient architecture:

1. **Physical Socket Factory ([`PhysicalNetworkSelector.kt`](https://developer.android.com/reference/android/net/ConnectivityManager)):**
   Queries `ConnectivityManager.getAllNetworks()`, selects active interfaces with `TRANSPORT_CELLULAR` or `TRANSPORT_WIFI` lacking `TRANSPORT_VPN`, and binds `OkHttpClient.socketFactory` directly to physical sockets. Bypasses system `tun0` routing without disconnecting the user's active VPN.
2. **Synchronous 0ms Offline Emergency Vault ([`OfflineCodeVault.kt`](https://developer.android.com/reference/androidx/security/crypto/EncryptedSharedPreferences)):**
   Caches door unlock codes in RAM and encrypted storage. When `openDoor()` fails or times out (2.5s), the controller **never retries network requests**, immediately surfacing the cached pin code.
3. **Direct GSM Hardware Forwarding:**
   Exposes the native API (`v2/app/phones-redirect`) to route incoming intercom rings over standard cellular telephony (GSM), answering calls and opening doors via DTMF tones with zero dependency on internet or push servers.
4. **Physical Metaphor UI:**
   Adheres to hardware instrumentation aesthetics: high-contrast 7-segment digital displays, mechanical toggles, desktop widgets, Android Quick Settings Tiles, and Wear OS 40mm round dial interfaces.

---

## Tooling & Reference Links

- **Binary Inspection & Analysis:**
  - [JADX Decompiler](https://github.com/skylot/jadx) — DEX to Java decompiler.
  - [Apktool](https://apktool.org/) — Tool for reverse engineering Android APK files.
  - [Android SDK Platform Tools (ADB)](https://developer.android.com/tools/adb) — Android Debug Bridge.
- **Local LLM Runtimes (8GB VRAM):**
  - [LM Studio](https://lmstudio.ai/) — Run local models with OpenAI-compatible REST server (`localhost:1234/v1`).
  - [vLLM](https://github.com/vllm-project/vllm) — High-throughput LLM inference engine.
  - [Ollama](https://ollama.ai/) — Lightweight local model runner.
- **Multi-Agent Orchestration:**
  - [cli-subagent](https://github.com/pacodelavega/cli-subagent) — Universal multi-account local CLI subagent router and provisioner.
- **Android Networking & Storage:**
  - [Square OkHttp](https://square.github.io/okhttp/) — HTTP client with custom SocketFactory support.
  - [Square Moshi](https://github.com/square/moshi) — Modern JSON library for Android.
  - [AndroidX Security Crypto](https://developer.android.com/reference/androidx/security/crypto/EncryptedSharedPreferences) — Encrypted key-value storage.

---

## License

This project and documentation are released under the [MIT License](LICENSE).
