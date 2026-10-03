# 외부 노트 검증 결과 — Apogee ONE v2 (0c60:0017)

> 이 문서는 사용자가 가져온 외부 연구 노트(주장 C1–C7)를 **1차 소스**에 대조해 검증한 결과다. 검증 데이터는 리서치 서브에이전트들이 실제로 각 소스를 열람(GitHub API·raw 파일·포럼·메일링리스트)한 3회 패스를 종합한 것이며, 본 세션에서 다시 재조회하지는 않았다. 소스가 서로 어긋나는 지점과 미공개(접근 불가) 항목은 그대로 명시한다. 우리 로컬 발견(Mac 업데이터 x86 디스어셈블 + 펌웨어 pypcode/AVR32 + 디스크립터 덤프)이 여전히 요청 의미·펌웨어 구조·윈도우 실패에 대한 1차 권위다.

## 요약 판정표

| 주장 | 내용 | 상태 | 핵심 |
|---|---|---|---|
| C1 | stevebrodie/apogee-one2-linux(2026): 전용 vendor init + 하드웨어 워치독 킵얼라이브, 녹음 O/재생 X | **부분확인** | 실질 전부 확인. 단 "0x29 ~9초마다"는 수치 혼동 — 실제 전송은 **4초**, 9초는 끊김 마감시한 |
| C2 | 킵얼라이브 = request 0x29, 6바이트 읽기 | **확인** | 우리 GetHardwareChanges와 바이트 단위로 동일 |
| C3 | 2022 alsa-devel/linux-usb 리셋 루프(Petr Janecek) = init/킵얼라이브 누락 탓 | **부분확인** | 스레드 실재 확인. "원인"은 합리적 **추론**이지 소스가 단언한 바 아님; 타이밍도 다름(~2초 vs ~9초) |
| C4 | Loopy Pro: Paa89가 업데이터 XML 편집→두 BIN 중 하나 로드, iPad Maestro로 입력/48V 제어 | **확인** | BIN 파일명·크기, 편집한 XML 필드는 **미공개** |
| C5 | PCB 사진에서 MCU = 32UC3A4 | **확인** | =AT32UC3A4(AVR32 UC3A4), 우리 pypcode AVR32 결과와 일치. 식별자는 Paa89가 아니라 포럼 유저 "uncledave" |
| C6 | Ghidra로 raw BIN 로드, 함수는 보이나 RE 미완, 2021-11 중단 | **확인** | 그대로 확인 |
| C7 | almog/apogee-one-usb-controller = ONE **v1**(0c60:0003), v2 아님 | **확인** | TAS1020 기반·표준 UAC2+vendor 2개뿐. 계보는 v1→v2가 아니라 **Duet(0016)→ONEv2(0017)** |

> 참고: 첫 번째 검증 패스는 담당 범위가 stevebrodie 레포로 한정돼 C4–C7을 "접근 불가(unreachable)"로 표기했으나, 2·3번째 패스가 Loopy Pro 포럼·GitHub를 직접 열람해 C4–C7을 확인했다. 따라서 전체적으로 진짜 접근 불가로 남은 것은 **포럼에서 끝내 공개되지 않은 세부(아래 (b))뿐**이다.

---

## 주장별 상세

### C1 — stevebrodie/apogee-one2-linux 존재·성격 — 부분확인
- **1차 소스가 말하는 것:** GitHub API상 created 2026-05-01, updated 2026-08-05, Python, MIT, 토픽 alsa/apogee/usb-audio, 포크 아님. README 축자: 기기 `0c60:0017, bcdDevice 1.05`; init은 "macOS에서 Wireshark로 Apogee Control2 앱 초기화를 캡처해 리버스"; "하드웨어 워치독이 대략 9초마다 USB에서 기기를 끊으며, 특정 vendor 명령(0x29)을 보내 리셋해야 함"; 상태표 — 녹음=Working, 안정 재생=미확인("스트림이 open 직후 즉시 실패").
- **우리 로컬과 대조:** 기기 식별(0c60:0017, 1.05)과 "녹음 O/재생 미완" 기대와 정확히 일치. **정정 1건:** 킵얼라이브 0x29는 **4초마다 전송**(코드 `time.sleep(4.0)`)이고, ~9초는 명령이 없을 때의 **끊김 마감시한**이다. 사용자 노트의 "0x29 ~9초마다"는 두 수치를 섞은 것. 워치독 자체는 정적 RE로는 드러나지 않는 **동적 사실**로, 우리 지도에 없던 조각이다.

### C2 — 킵얼라이브 = 0x29, 6바이트 읽기 — 확인
- **1차 소스:** `apogee-one-keepalive.py`에서 읽기 헬퍼 `r(dev,req,ln,idx=0) = dev.ctrl_transfer(0xc0, req, 0, idx, ln, TIMEOUT)`. heartbeat 스레드가 `r(dev, 0x29, 6)`을 4초마다 호출. 주석: "watchdog 명령(0x29)은 init 시퀀스의 부분집합을 heartbeat로 바꿔가며 **이진 탐색**으로, 9초 끊김을 막는 단 하나의 명령을 찾아낸 것."
- **우리 로컬과 대조:** **완전 일치.** bmRequestType 0xC0(읽기), bRequest 0x29, wValue 0, wIndex 0, wLength 6 — 우리 `0x29 = GetHardwareChanges(6바이트 읽기)`와 request 번호·방향(IN)·길이가 모두 같다.
- **"0x29 킵얼라이브"는 우리 0x29와 같은 것인가? → 그렇다.** 동일한 단 하나의 request다. 레포 저자는 의미명을 몰라 "watchdog"이라 부르며 브루트포스로 찾았고, 우리 Mac 업데이터 디스어셈블이 그 의미명(GetHardwareChanges)을 공급한다. 즉 **하드웨어 변경 폴링을 하는 6바이트 읽기 자체가 부수효과로 워치독 타이머를 리셋**한다. 별도의 "킵얼라이브 전용" request가 아니다.

### C3 — 2022 리셋 루프 스레드 — 부분확인
- **1차 소스:** linux-usb/alsa-devel, 2022-03. spinics `msg224111` = Petr Janecek 원글(기기 `idVendor=0c60 idProduct=0017`, product "ONEv2", serial `0C12FF…9B`, bcdDevice 1.05, kernel 5.16.16): "2초쯤마다 계속 리셋", "snd-usb-audio 드라이버를 꺼도 리셋됨 → 더 낮은 레벨 문제". 드라이버 켜면 `cannot get min/max values for control 2 (id 10)/(id 12)/(id 14)` 반복 후 연결→~600–700ms 제어 에러→USB 끊김→즉시 재연결. marc.info `m=164797225004283`은 이 스레드의 **Alan Stern 답글**(usbmon 트레이스 요청, USB runtime PM 끄기 `echo -1 >/sys/module/usbcore/parameters/autosuspend`).
- **우리 로컬과 대조:** 에러 시그니처 `control 2 (id 10/12/14)`는 UAC2 드라이버가 feature unit 10/12/14에서 볼륨(제어 선택자 2) 범위를 못 읽는 것 = proprietary init 전에는 죽어 있는 마이크 게인 유닛들로, stevebrodie의 clock.c 패치+`ignore_ctl_error=1`이 우회하는 바로 그 지점. **근본 원인(init 누락)은 일관.** 다만 두 가지 주의:
  1. "init/킵얼라이브 누락이 원인"은 **우리가 끌어내는 추론**이지 레포도 스레드도 단언하지 않는다(레포는 스레드를 인용조차 안 함).
  2. **타이밍이 다름** — Janecek의 ~2초 리셋은 snd-usb-audio를 꺼도 지속(= 열거/핸드셰이크 실패 레벨의 리셋)이고, stevebrodie의 ~9초는 init 이후의 워치독이다. 서로 다른 두 메커니즘일 가능성이 높아 "하나로 설명"은 두 간격을 뭉뚱그린 것.
- **"0xEE string request" 언급(과제 각도):** 가져온 어떤 메일 메시지에도 근거 없음 → 미지지.

### C4 — 두 BIN + 편집 가능 XML 매니페스트 — 확인
- **1차 소스:** Loopy Pro 스레드 47616, Paa89(2021-11) 축자: "업데이트 디렉터리에 Apogee One용 bin 파일이 **둘** 있어서, Firmware updater에게 다른 BIN을 로드하도록 시켰다", "한 일은 업데이트 디렉터리의 **XML 파일을 Visual Studio로 편집**한 것뿐". 결과: USB-C iPad Pro 11의 Apogee Maestro가 기기를 보게 됐고 입력 종류·+48V를 바꿀 수 있었으나 "아직 어떤 오디오 앱도 입력을 못 봄". 덤: "Apogee 자체 케이블 말고 다른 USB 케이블을 꽂으면 Maestro가 감지됨".
- **우리 로컬과 대조:** "두 bin"은 우리 dual-bank `ONEv2_USB_Audio_Image0.bin / Image1.bin`과 부합. 평문 XML을 고쳐 **대체 BIN을 성공적으로 플래시**했다는 사실은 업데이터가 이미지에 **서명/진위 검사를 강제하지 않는다**는 독립 증거 — 우리의 "두 이미지 말미 4바이트 `0x00000A94`가 동일 = 콘텐츠 체크섬 아님", "평문" 결론과 합치. 날짜 정정: **2021-10~11**.

### C5 — MCU = 32UC3A4 — 확인
- **1차 소스:** 같은 스레드(2021-10), 포럼 유저 **uncledave**: "사진 속 32UC3A4 칩이 마이크로컨트롤러"(Microchip 데이터시트 링크). Paa89가 PCB 사진 제공.
- **우리 로컬과 대조:** `32UC3A4` = Atmel/Microchip **AT32UC3A4**(AVR32 UC3A3/A4 패밀리) — 우리 pypcode(Ghidra AVR32 디코더) 결과(리셋 벡터 0x80000000, program_start 0x80004000, SP=0x10000/64KB SRAM)와 **동일 칩 패밀리**. 육안 식별(포럼)과 ISA 증명(우리)이 서로를 보강. **귀속 정정:** 노트는 C5를 Paa89 공으로 적었으나 실제 식별자는 uncledave.

### C6 — Ghidra RE 미완 — 확인
- **1차 소스:** Paa89(2021-11): "Ghidra로 RAW Bin을 못 봄. 함수 등은 보임. 구글링하면 언젠가 리버스할지도." 스레드의 마지막 기술 글.
- **우리 로컬과 대조:** raw BIN을 Ghidra에 올려 함수는 봤으나 의미 RE·ISA 확정은 못 함, 2021-11 중단. 우리 작업(pypcode AVR32 확정, 리셋/startup 추적, dual-bank +0x20000 reloc 분석)이 훨씬 앞섬 — Paa89는 **미완의 선행자**이지 우리를 능가하는 소스가 아님.

### C7 — almog = ONE v1(0c60:0003) — 확인
- **1차 소스:** almog/apogee-one-usb-controller(Objective-C, 2026-05-03, MIT). README: "오리지널 Apogee ONE USB `0x0c60:0x0003` 전용", macOS Tahoe 26.3.1에서 테스트. `tools/one-control/main.m`: `kApogeeVendorID=0x0c60, kApogeeOneProductID=0x0003`. `docs/legacy-one-reverse-engineering.md`: v1은 **TAS1020**(TI 8051 계열) 기반, 표준 UAC2 사용 — Selector Unit 7(1→FU5 Int, 2→FU11 Ext, 3→FU13 Ext48V, 4→FU9 Inst), 게인 FU5/9/11/13, 메인 FU2, 헤드폰 FU22 — vendor는 **단 2개**: `0x06`(LLM 출력 감쇠, bmRequestType 0x40/wValue=-dB signed16/wLength 0), `0x02`(TAS1020 RemoteI2C 모니터 믹스, wValue 0x2b50/wIndex=ext_mic_level/payload `0x40|level`, 0=최대…63=무음 반전).
- **우리 로컬과 대조:** v1(0c60:0003)은 우리 타깃 v2(0c60:0017)와 **다른 기기·다른 아키텍처**(TAS1020 vs AVR32 UC3A4; 표준 UAC2+vendor 2개 vs 대형 vendor 세트+워치독). v1의 코드(`0x06`, `UpdateLLM`, RemoteI2C)를 v2에 적용하면 안 됨. 실제 프로토콜 계보는 **Duet(0016)→ONEv2(0017)**.

---

## (a) 초기화·킵얼라이브 프로토콜 — 구체 바이트

모두 `apogee-one-keepalive.py` 축자. 헬퍼:
- 읽기 `r(dev,req,ln,idx=0) = dev.ctrl_transfer(0xc0, req, 0, idx, ln, TIMEOUT)` → bmRequestType **0xC0**, wValue 0, wIndex 0
- 쓰기 `w(dev,req,data,idx=0) = dev.ctrl_transfer(0x40, req, 0, idx, bytes(data), TIMEOUT)` → bmRequestType **0x40**, wValue 0, wIndex 0
- `TIMEOUT = 200`(ms), VID/PID `0x0c60/0x0017`. 모든 전송은 EP0 기본 제어 파이프(wIndex 0) — 우리 vendor IF3 bulk 엔드포인트는 쓰지 않음.

**`full_init()` 순서(이 순서 자체가 우리에게 새 정보):**
```
reads : (0x29,6) (0x31,4) (0x29,6) (0x1f,1) (0x20,1) (0x28,3) (0x36,1)
write : 0x34 <- [0x17]
reads : (0x44,1) (0x3e,1) (0x33,1) (0x35,1) (0x53,1)
write : 0x10 <- [0x00]
```
**킵얼라이브/워치독:** `r(dev, 0x29, 6)`를 **4.0초마다**. 주석 "이 명령이 없으면 ONEv2는 ~9초 후 USB에서 끊김." 9000+ 사이클 안정 확인.

**브링업 흐름:** `wait_for_device → dev.reset() → set_configuration() → full_init() → modprobe snd_usb_audio ignore_ctl_error=1 → heartbeat 스레드 시작`. `find_and_unbind()`가 sysfs 이름을 `/sys/bus/usb/drivers/usb/unbind`에 써서 libusb가 기기를 claim. 캡처 출처는 README는 "Control2 앱", keepalive.py 독스트링은 "Maestro 앱"으로 **레포 내부 명칭 불일치** 있음.

**"0x29 keepalive" ≡ 우리 0x29(GetHardwareChanges 읽기)?** → **예, 완전히 동일.** 같은 bRequest·같은 IN 방향·같은 6바이트. 워치독 리셋은 그 6바이트 읽기의 부수효과. 별개 request 아님.

**우리 의미 지도와 교차 확인(일치):** `0x29`=GetHardwareChanges(r6) / `0x28`=fw버전·UID(r3) / `0x34`=마이크 게인(w, `0x17`=23) / `0x3e`=인스트 게인(r) / `0x53`=출력 라우트(r) / `0x36`=마이크 입력 종류(여기선 **읽기** → get/set 양방향 시사).

**우리 표에 없던 새 opcode 7개:** `0x31`(r4), `0x1f`(r1), `0x20`(r1), `0x33`(r1), `0x35`(r1), `0x44`(r1), `0x10`(w `[0x00]`, 스트림/클록 enable 추정).
- **Duet(take_control, 0c60:0016) 매핑으로 일부 의미 추정 가능:** Duet OUTPUT LEVEL=`0x33`, OUTPUT MUTE=`0x35`, INPUT GROUP=`0x44` → ONEv2의 `0x33/0x35/0x44`도 각각 출력 레벨·출력 뮤트·입력 그룹 읽기일 공산. `0x31/0x1f/0x20/0x10`은 Duet 맵에도 없어 **미해독** — 우리 펌웨어 디스어셈블로 디코딩할 과제.

---

## (b) 두 BIN·XML·업데이터 무결성 — 새로 밝혀진 것 / 미공개

- **새로 확인:** 업데이터 "update directory"에 **XML 매니페스트 + 두 개의 ONE용 BIN**이 있고, Paa89가 평문 XML을 편집해 updater가 **대체 BIN**을 로드하도록 바꿨으며 기기가 이를 받아들여 동작했다. → 업데이터는 로드 이미지에 대해 **서명/무결성 검사를 강제하지 않는다**(또는 매우 약함). 우리의 "평문 이미지 + 말미 4바이트 `0x00000A94` 동일(콘텐츠 체크섬 아님)" 결론과 합치. (업데이터는 **페이지 리드백**으로 검증 — 이는 우리 로컬 발견.)
- **미공개(포럼에서 끝내 안 나옴 = 접근 불가):**
  - 두 BIN의 **정확한 파일명·바이트 크기** — 미공개. 따라서 Paa89의 "두 bin"을 우리 `Image0/Image1`에 **이름으로 매핑 불가**.
  - 편집한 **XML의 구체 요소/필드·스키마** — 미공개.
  - 매니페스트의 체크섬/서명 **필드명** — 언급 없음.
- **stevebrodie 레포에는 펌웨어·BIN·XML·업데이터가 전혀 없음**(런타임 전용). BIN/XML 각도는 전적으로 Loopy Pro(C4) 소스뿐. 뱅크 주소·reloc·DFU 부트로더 구조 같은 세부는 전부 우리 로컬 작업이 공급(bank0 @0x80004000, bank1 @0x80024000, 662 diff 전부 +0x20000, DFU는 미배포 첫 0x4000 부트로더).

---

## (c) 우리가 이미 가진 것 vs 외부가 새로 주는 것

**외부가 새로 주는 것(우리에 없던 것):**
1. **하드웨어 워치독 동작** — 주기적 vendor 제어 전송이 없으면 ~9초 내 자가 끊김, `0x29` 읽기 하나로 타이머 리셋, 4초 heartbeat면 충분. 정적 RE로는 못 얻는 동적 사실이자 **2022 리눅스 리셋 루프의 유력 근본 원인**.
2. **실제 macOS 캡처 기반의 순서 있는 init 시퀀스 + 페이로드**(위 (a)) — 우리는 request 의미는 알았으나 구체 순서·값(`0x34<-0x17`, `0x10<-0x00`)은 없었음.
3. **새 opcode 7개**(0x31, 0x1f, 0x20, 0x33, 0x35, 0x44, 0x10).
4. **동작하는 ALSA 커널 패치 2개 + 환경 설정:**
   - `sound/usb/clock.c` `uac_clock_source_is_valid()`를 쿼리 실패 시 `return false`→**`return true`**.
   - `sound/usb/media.c` `snd_media_stream_init()`에서 `media_create_pad_link()` 실패 시 `goto remove_intf_link`→**`continue`**(비치명화).
   - `snd_usb_audio ignore_ctl_error=1`, WirePlumber `api.alsa.use-acp=false`(*ONEv2*).
   - 단, 이 전부로도 **재생은 PCM open 직후 실패**("File descriptor in bad state" / "No such device or address"). 녹음만 동작.
5. **Duet(0c60:0016) 전체 vendor 맵**(take_control) — 같은 패밀리 **제3의 기기**가 우리 v2 규약(0x40/0xC0, wValue 0, 1바이트)과 `0x34`(마이크 게인)·`0x3e`(인스트)·`0x53`(출력)을 **정확히** 재확인. **Duet→ONEv2 계보** 성립. (Duet엔 0x29·init·킵얼라이브가 **없음** → 워치독+init은 AVR32 ONEv2에서 새로 생긴 요구.)
6. **마이닝 가능한 raw USB 캡처:** `everything.pcapng.zip`(15,572,173 B), `host.pcapng`(434,148 B), `apogee-init.pcapng`(480 B).
7. **독립 MCU 육안 ID(32UC3A4)** — 우리 AVR32 결과 보강.
8. **ALSA 실패 시그니처+환경**(`cannot get min/max values for control 2 (id 10/12/14)`, kernel 5.16.16, serial `0C12FF…9B`).

**우리 로컬이 가졌고 외부엔 없는 것(우리가 권위):**
- vendor request의 **1차 의미명**(Apogee 자체 심볼 업데이터에서): `0x36` SetMicInputType{0=Int,1=Ext,2=Ext48V}, `0x29` GetHardwareChanges, `0x34` 마이크 게인, `0x3e` 인스트 게인, `0x48` GetEncoderSelect, `0x53` 출력, `0x26` identify, `0x28` fw/UID, `0x14` 미터. (stevebrodie는 0x29만, 그것도 "watchdog"으로만 알고 나머지는 불투명; Duet은 다른 기기.)
- **펌웨어 RE 전반:** pypcode로 AVR32 ISA 증명, 리셋 벡터→program_start→_stext, 64KB SRAM, dual-bank +0x20000 reloc, 버전 1.5.0(=1.05), DFU는 미배포 부트로더.
- **윈도우 스토리 전체:** `usbaudio2.sys` FAILS_START `0xC0440022`(Event ID 34)와 후보 디스크립터 결함(중복 CLOCK_SOURCE id 1, IAD 안의 vendor IF3, feature-unit bLength 10 vs 18, AC wTotalLength 174 vs 167) — 어떤 외부 소스도 윈도우를 다루지 않음.
- **전체 UAC2 디스크립터 덤프:** SELECTOR UNIT id 15(터미널 9/11/13), vendor IF3(0xFF/0xF0 bulk+interrupt).

---

## (d) 수정이 필요한 우리 기존 결론

1. **"윈도우 실패 = 디스크립터 결함" 단정은 완화해야 함(가장 중요).**
   외부 증거는 **두 번째, 독립적인 실패 층**이 있음을 보여준다: 기기는 proprietary vendor init이 돌기 전까지 **클록 유효성 질의에 응답하지 않고**, init 뒤에도 하드웨어 워치독이 돌아간다. 리눅스에서 clock.c 패치(유효성 쿼리 실패 시 true 반환)가 필요했다는 것이 그 증거다.
   - 단, **"0xC0440022 = 클록 유효성 거부"라는 JSON 일부 패스의 해석에는 주의가 필요**하다. 우리 로컬 근거는 `0xC0440022`를 usbaudio2 Event ID 34 **"descriptor not compliant"**(파싱 단계의 정적 거부)에 묶는다. 한 검증 패스가 이를 리눅스 clock-validity 문제와 같은 원인으로 **과매핑**했을 수 있다. 두 가지는 **구분**해야 한다: (i) 정적 디스크립터 비준수 → usbaudio2가 아예 start 거부(윈도우); (ii) 동적 init/클록-유효성/워치독 → 드라이버가 붙어도 스트림 불가(리눅스는 ALSA가 더 관대해 더 멀리 감).
   - **실무적 수정 결론:** 디스크립터 결함을 고치는 것이 윈도우 start에 **필요**할 수는 있어도 **충분하지 않다.** init/클록-유효성/워치독이라는 둘째 층 때문에 "디스크립터만 패치하면 윈도우에서 동작"은 **입증되지 않음**. 디스크립터 수정과 init/킵얼라이브 양쪽을 다뤄야 한다. `0xC0440022`의 정확한 의미(정적 파싱 거부 vs 클록 거부)는 윈도우에서 **재확인 과제**.
2. **킵얼라이브 간격:** 우리/사용자 노트의 "0x29 ~9초"는 정정 — **전송은 4초마다**, 9초는 끊김 마감시한.
3. **`0x36` 입력 종류:** Duet은 입력 TYPE에 `0x16`을, `0x36`은 믹서 SOFTWARE_RETURN_SOURCE에 쓴다. v2는 `0x36`=입력 종류. **제품별 번호 재배치**로 보이며(우리 Mac 업데이터 심볼 + stevebrodie의 init `0x36` 읽기로 **이중 출처**라 반박 아님) — 우리 디스어셈블에서 한 줄 재확인 권장.
4. **`0x21` phantom(잠정) 미지지:** Duet phantom은 `0x15`. 단일 입력 ONE에서 48V는 별도 request가 아니라 **SetMicInputType 값 2(Ext48V)**로 접힐 가능성이 큼 → `0x21`은 **미검증**으로 표기.
5. **C5 귀속:** 32UC3A4 식별자는 Paa89가 아니라 포럼 유저 **uncledave**.
6. **C4 날짜:** "2020–2021"이 아니라 **2021-10~11**.
7. **"0xEE string request"**(과제 각도): 어떤 소스에도 근거 없음 → **미지지**로 둠.
8. **다른 ONEv2 RE는 사실상 이 네 소스뿐:** GitHub 토픽 `apogee`에도 stevebrodie + matt8707/duet2-startup(Duet-2 자동화)뿐. 2026-05 LKML "iface reset quirk" 패치는 TAE1159 `25aa:600b`용으로 **무관**(오판 배제).

---

## (e) 참고 링크

**stevebrodie/apogee-one2-linux (C1/C2, 프로토콜 1차 소스)**
- https://github.com/stevebrodie/apogee-one2-linux
- https://api.github.com/repos/stevebrodie/apogee-one2-linux
- https://api.github.com/repos/stevebrodie/apogee-one2-linux/contents/
- https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/README.md
- https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one-keepalive.py
- https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/0001-ALSA-usb-audio-return-true-for-clock-validity-on-query-failure.patch
- https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/0002-ALSA-usb-audio-make-media-pad-link-failure-non-fatal.patch
- https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one.service

**2022 리셋 루프 스레드 (C3)**
- https://www.spinics.net/lists/linux-usb/msg224111.html  (Petr Janecek 원글)
- https://www.spinics.net/lists/linux-usb/msg224275.html
- https://marc.info/?l=alsa-devel&m=164797225004283  (Alan Stern 답글)

**Loopy Pro 스레드 47616 (C4/C5/C6)**
- https://forum.loopypro.com/discussion/47616/how-hard-is-it-to-hack-reverse-engineer-an-audio-interface
- https://forum.loopypro.com/discussion/comment/1011044
- https://forum.loopypro.com/discussion/comment/1011073
  (핵심 후속 코멘트: 1011776 XML/BIN 편집, 1011053/1011061 32UC3A4, 1012114 Ghidra)

**almog/apogee-one-usb-controller = ONE v1 0c60:0003 (C7)**
- https://github.com/almog/apogee-one-usb-controller
- https://api.github.com/repos/almog/apogee-one-usb-controller
- https://raw.githubusercontent.com/almog/apogee-one-usb-controller/main/README.md
- https://raw.githubusercontent.com/almog/apogee-one-usb-controller/main/docs/legacy-one-reverse-engineering.md
- https://raw.githubusercontent.com/almog/apogee-one-usb-controller/main/tools/one-control/main.m

**stefanocoding/take_control = Apogee Duet 0c60:0016 (신규 교차검증, Duet→ONEv2 계보)**
- https://github.com/stefanocoding/take_control
- https://api.github.com/repos/stefanocoding/take_control
- https://raw.githubusercontent.com/stefanocoding/take_control/master/take_control.py

**오판 배제용**
- https://github.com/topics/apogee
- https://ratatoskr.run/lkml/2026/05/17034279/t  (TAE1159 25aa:600b용, 무관)

> 주의: 위 링크·축자 인용은 **리서치 서브에이전트의 열람 결과(관찰된 제3자 데이터)**이며 본 세션에서 재조회하지 않았다. 그중에서도 가장 실행가치가 높은 것은 stevebrodie의 **init+4초 킵얼라이브**와 **pcap 3종**이며, 다음 작업으로 `everything.pcapng.zip`를 받아 우리 의미 지도에 대조하면 새 opcode 7개(특히 0x31/0x1f/0x20/0x10)를 디코딩할 수 있다. 다만 파일 다운로드는 사용자 승인이 필요하다.",
    "angles": [
      {
        "summary": "Examined github.com/stevebrodie/apogee-one2-linux in depth (API metadata, README, the keepalive daemon source, both kernel patches, the systemd unit). The repo is REAL and first-party reverse-engineering work: created 2026-05-01, pushed 2026-05-03, updated 2026-08-05, default branch main, MIT, Python, ~14.8 MB (mostly a 15.5 MB everything.pcapng.zip USB capture). It targets exactly our device (0c60:0017, bcdDevice 1.05) and strongly cross-validates our vendor control protocol. KEY RECONCILIATIONS: (1) The keepalive IS request 0x29 as a READ of 6 bytes (bmRequestType 0xc0, wValue 0, wIndex 0) - byte-for-byte identical to our GetHardwareChanges - so C2 is CONFIRMED. (2) But the user's "every ~9 seconds" is a conflation: ~9 s is the hardware-watchdog DISCONNECT timeout; the 0x29 keepalive is actually sent every 4 seconds. (3) Recording works, playback fails immediately after open - CONFIRMED verbatim. The repo also supplies something new to us: the exact Maestro/Control2 bring-up INIT ORDER with payloads, several vendor requests not in our table (0x31,0x1f,0x20,0x33,0x35,0x44,0x10), the watchdog behavior itself, and two one-line ALSA kernel patches (clock-validity and media-pad-link) - the Linux analog of our Windows 0xC0440022 clock-validity rejection. The repo does NOT identify the MCU, has no firmware bins/XML/DFU analysis (that is the Paa89 angle, not here), does not reference our vendor interface 3 or the standard UAC2 selector unit id 15, and does not cite the Janecek/alsa-devel thread (though its watchdog finding plausibly explains that historical reset loop).",
        "verifications": [
          {
            "claim_id": "C1",
            "status": "partly",
            "what_the_source_says": "Confirmed: repo exists, is a 2026 project (created_at 2026-05-01T18:41:15Z, pushed_at 2026-05-03, updated_at 2026-08-05), targets 0c60:0017. README states verbatim 'Device: Apogee ONEv2 (USB VID:PID 0c60:0017, bcdDevice 1.05)'. Confirmed: proprietary init sequence reverse-engineered ('The init sequence was reverse-engineered by capturing USB traffic with Wireshark on macOS while the Apogee Control2 app initialised the device'). Confirmed: periodic vendor keepalive/watchdog ('The ONEv2 has a hardware watchdog that disconnects the device from USB approximately every 9 seconds'; 'sends a 0x29 vendor read every 4 seconds to reset the hardware watchdog'). Confirmed: recording works, playback incomplete ('Capture (recording): Working'; 'Stable playback audio: Stream fails immediately after opening - no audio confirmed yet'). CORRECTION: the phrase 'request 0x29 ~every 9 seconds' conflates two separate numbers. ~9 s is the DISCONNECT/watchdog timeout; the 0x29 keepalive is SENT every 4 seconds (time.sleep(4.0) in heartbeat_thread; code comment 'sends that command every 4 seconds').",
            "reconciliation_with_local": "Device identity (0c60:0017, ONEv2, bcdDevice 1.05) matches our USB descriptor dump exactly. The one factual slip in the note is the keepalive interval: it is 4 s, not 9 s; 9 s is the watchdog disconnect period. Everything else in C1 is correct.",
            "sources": [
              "https://api.github.com/repos/stevebrodie/apogee-one2-linux",
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/README.md",
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one-keepalive.py"
            ]
          },
          {
            "claim_id": "C2",
            "status": "confirmed",
            "what_the_source_says": "The keepalive is request 0x29 and it is a READ of 6 bytes. In the source: heartbeat_thread calls r(dev, 0x29, 6); helper r() does dev.ctrl_transfer(0xc0, req, 0, idx, ln, TIMEOUT) with idx=0 -> bmRequestType 0xc0 (device-to-host/read, vendor, device), bRequest 0x29, wValue 0, wIndex 0, wLength 6. The same 0x29/6-byte read also appears twice in the init sequence. Docstring: 'The watchdog command (0x29) was isolated by binary search - testing subsets of the init sequence as the heartbeat until the single command that prevented the 9-second disconnect was found.'",
            "reconciliation_with_local": "EXACT match to our local finding that 0x29 = GetHardwareChanges, a READ returning 6 bytes (bmRequestType 0xC0, wValue 0, wIndex 0). Same request number, same direction (IN), same length. The repo author did not know its semantic name; they empirically repurposed our GetHardwareChanges poll as the watchdog-reset heartbeat. So yes - it is genuinely 0x29, genuinely a read, and genuinely the same request we catalogued.",
            "sources": [
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one-keepalive.py"
            ]
          },
          {
            "claim_id": "C3",
            "status": "partly",
            "what_the_source_says": "The alsa-devel thread is confirmed real: marc.info/?l=alsa-devel&m=164797225004283 is subject 'Re: Apogee ONEv2 keeps resetting', dated 2022-03-22, device 'idVendor=0c60, idProduct=0017, bcdDevice=1.05'; the original poster reported the device 'keeps resetting every two seconds or so. It keeps resetting even when the snd-usb-audio driver is disabled, so the problem is probably at a lower level'; this specific message is Alan Stern's reply (suggesting usbmon trace + disabling USB runtime PM). The stevebrodie README/code does NOT cite this thread, Petr Janecek, marc.info, or alsa-devel anywhere (reference/credits section ABSENT; only Related Project is take_control for the Duet 0c60:0016).",
            "reconciliation_with_local": "The repo's independent discovery - a hardware watchdog that disconnects the device unless a vendor control transfer is periodically issued, plus a missing proprietary init - is a plausible and technically consistent root cause for that 2022 reset loop (resets persist even with snd-usb-audio disabled = below the audio driver = firmware watchdog, matching the repo). So the EXPLANATION in C3 is plausible, but it is an inference we are drawing, not something either source asserts: the repo never links to the thread, and the reported reset cadence differs (OP '~two seconds', repo '~9 seconds'). I could not independently confirm the OP was Petr Janecek from this single message (it returned Alan Stern as the author of m=...04283, i.e. the reply).",
            "sources": [
              "https://marc.info/?l=alsa-devel&m=164797225004283",
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/README.md"
            ]
          },
          {
            "claim_id": "REPO-vs-REQUEST-TABLE",
            "status": "confirmed",
            "what_the_source_says": "The init sequence (full_init) and keepalive issue these vendor requests. READS (bmRequestType 0xc0, wValue 0, wIndex 0): 0x29 len6, 0x31 len4, 0x29 len6, 0x1f len1, 0x20 len1, 0x28 len3, 0x36 len1, then 0x44 len1, 0x3e len1, 0x33 len1, 0x35 len1, 0x53 len1. WRITES (bmRequestType 0x40, wValue 0, wIndex 0): 0x34 data [0x17]; 0x10 data [0x00]. Keepalive: 0x29 len6 read every 4 s. TIMEOUT=200 ms.",
            "reconciliation_with_local": "Strong cross-validation of our request table: 0x29 read-6 = our GetHardwareChanges (match); 0x28 read-3 = our fw version/UID (match, read); 0x34 write = our mic gain (match, write; payload 0x17=23 is a gain value); 0x3e read-1 = our inst gain (match); 0x53 read-1 = our output route (match). 0x36 read-1: our table has 0x36 = SetMicInputType as a WRITE - repo READS it here, implying a bidirectional get/set on the same request. Repo does NOT use our 0x48 (GetEncoderSelect), 0x26 (identify), or 0x14 (meter data). Repo uses several requests ABSENT from our table: 0x31 (read 4), 0x1f (read 1), 0x20 (read 1), 0x33 (read 1), 0x35 (read 1), 0x44 (read 1), 0x10 (write [0x00]). All transfers are on the EP0 default control pipe (wIndex 0) - none use our vendor interface 3 bulk endpoints.",
            "sources": [
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one-keepalive.py"
            ]
          },
          {
            "claim_id": "REPO-vendor-IF3-and-selector",
            "status": "confirmed",
            "what_the_source_says": "README query for 'selector unit', 'vendor interface', 'interface 3', 'class 0xFF', 'standard UAC2 requests', and for input-source/mic-type/+48V/gain control all returned ABSENT. All control traffic in the code targets wIndex 0 on the default control endpoint; no bulk/interrupt interface is claimed or opened.",
            "reconciliation_with_local": "The repo does NOT reference our vendor-specific interface 3 (class 0xFF/subclass 0xF0 with bulk in/out + interrupt in), and does NOT use the standard UAC2 SELECTOR UNIT id 15 we found in the descriptor dump. It drives input type/gain purely through vendor EP0 requests (e.g. 0x34 write, 0x36). Consistent with our dump but narrower: the author appears unaware of both the standard selector unit and the vendor bulk interface.",
            "sources": [
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/README.md",
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one-keepalive.py"
            ]
          },
          {
            "claim_id": "C4-C7",
            "status": "unreachable",
            "what_the_source_says": "Not addressed by this source. The stevebrodie repo contains no firmware .BIN files, no XML manifest, no updater, no MCU part-number identification, and no reference to the Loopy Pro forum, Paa89, the 32UC3A4, Ghidra work, or the almog ONE v1 (0c60:0003) controller. The only cross-reference is 'Related Projects: take_control (Apogee Duet, 0c60:0016)'.",
            "reconciliation_with_local": "C4 (Paa89 two BINs + XML flash), C5 (32UC3A4 MCU ID), C6 (Ghidra), and C7 (almog v1 repo) must be verified from the Loopy Pro forum threads and those GitHub repos directly - this repo (the assigned angle) does not speak to them.",
            "sources": [
              "https://api.github.com/repos/stevebrodie/apogee-one2-linux/contents/",
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/README.md"
            ]
          }
        ],
        "protocol_details": "ALL verbatim from apogee-one-keepalive.py. Helper definitions: r() = dev.ctrl_transfer(0xc0, req, 0, idx, ln, TIMEOUT) [vendor READ, idx defaults 0]; w() = dev.ctrl_transfer(0x40, req, 0, idx, bytes(data), TIMEOUT) [vendor WRITE]. TIMEOUT = 200 (ms). VID/PID = 0x0c60/0x0017.

INIT SEQUENCE (full_init), in exact order:
  READS (bmRequestType 0xc0, wValue 0, wIndex 0, wLength = ln):
    0x29 (6), 0x31 (4), 0x29 (6), 0x1f (1), 0x20 (1), 0x28 (3), 0x36 (1)
  WRITE: 0x34 <- data [0x17]  (bmRequestType 0x40, wValue 0, wIndex 0, 1 byte)
  READS: 0x44 (1), 0x3e (1), 0x33 (1), 0x35 (1), 0x53 (1)
  WRITE: 0x10 <- data [0x00]  (bmRequestType 0x40, wValue 0, wIndex 0, 1 byte)
Source literal:
  for req, ln in [(0x29, 6), (0x31, 4), (0x29, 6), (0x1f, 1), (0x20, 1), (0x28, 3), (0x36, 1)]: r(dev, req, ln)
  w(dev, 0x34, [0x17])
  for req, ln in [(0x44, 1), (0x3e, 1), (0x33, 1), (0x35, 1), (0x53, 1)]: r(dev, req, ln)
  w(dev, 0x10, [0x00])

KEEPALIVE / WATCHDOG (heartbeat_thread):
  r(dev, 0x29, 6)  -> bmRequestType 0xc0, bRequest 0x29, wValue 0, wIndex 0, wLength 6
  time.sleep(4.0)  -> interval = 4.0 seconds (NOT 9). Comment: 'The ONEv2 disconnects from USB after ~9 seconds without this command.' Logs cycles as cycles*4 s. Device declared lost after >3 consecutive heartbeat errors.

Bring-up flow (main loop): wait_for_device -> dev.reset() -> set_configuration() -> full_init() -> modprobe snd_usb_audio ignore_ctl_error=1 (via 'modprobe --ignore-install snd_usb_audio ignore_ctl_error=1') -> start heartbeat thread. find_and_unbind() writes the device sysfs name to /sys/bus/usb/drivers/usb/unbind so libusb can claim it. All control transfers use wIndex 0 (default control pipe); no bulk/interrupt interface (our vendor IF3) is opened. No standard UAC2 selector-unit (SET/GET CUR on unit id 15) request is used - input/gain is driven by vendor requests 0x34 (write) and 0x36. Discovery method (README): 'reverse-engineered by capturing USB traffic with Wireshark on macOS while the Apogee Control2 app initialised the device' (note: the keepalive.py docstring instead says 'the Apogee Maestro app' - an internal naming inconsistency within the repo). Watchdog command isolated 'by binary search - testing subsets of the init sequence as the heartbeat'.",
        "bin_xml_details": "NONE in this repo. The stevebrodie project is Linux runtime only: it contains no firmware .BIN files, no XML manifest, no Apogee updater, and performs no updater/integrity analysis. There is therefore nothing here about the two ONE .BIN files or the editable XML manifest (that is the Paa89 / Loopy Pro angle, C4, which must be checked on forum.loopypro.com and in an actual Apogee updater, not in this repo). What this repo DOES carry as binaries are USB captures, not firmware: everything.pcapng.zip (15,572,173 bytes), host.pcapng (434,148 bytes), and apogee-init.pcapng (480 bytes) - Wireshark traces of the macOS init, from which the init/keepalive sequences above were extracted. No MCU identification and no bootloader/DFU discussion anywhere in the repo.",
        "new_vs_known": "GENUINELY NEW (beyond our local disassembly): (1) The exact host-side BRING-UP ORDER and payloads that Apogee's macOS app sends - our x86 disassembly gave us the request semantics but not the concrete init ordering/values. Specifically the two writes 0x34<-[0x17] (mic gain = 23) and the final 0x10<-[0x00], plus the ordered read sweep. (2) Vendor requests NOT in our table: 0x31 (read, 4 bytes), 0x1f (read, 1), 0x20 (read, 1), 0x33 (read, 1), 0x35 (read, 1), 0x44 (read, 1), 0x10 (write, [0x00]) - seven new opcodes to fold into our table. (3) The HARDWARE WATCHDOG behavior itself: the device self-disconnects/resets ~every 9 s unless a vendor control transfer is issued; any 0x29 read resets the timer; a 4 s heartbeat is sufficient. This is a dynamic/behavioral fact our static RE could not have revealed, and it is the likely root cause of the 2022 alsa-devel reset loop. (4) Two concrete Linux kernel defects + one-line fixes: sound/usb/clock.c uac_clock_source_is_valid() returns false on a failed clock-validity query (patch: return true), and sound/usb/media.c snd_media_stream_init() does 'goto remove_intf_link' on media_create_pad_link() failure (patch: continue). The clock.c issue is the LINUX ANALOG of our Windows usbaudio2.sys 0xC0440022 clock-validity rejection - same underlying cause (device won't answer clock-validity until vendor-initialised), different OS. (5) Open problem documented: even with init + keepalive + both patches, playback 'stream fails immediately after opening - no audio confirmed'; capture/recording works.

WHAT OUR LOCAL WORK HAS THAT THIS REPO LACKS: MCU identification (AVR32 UC3A3/A4 - repo never IDs the chip); firmware images, dual-bank layout, DFU/bootloader analysis; the SEMANTIC request table (0x36 SetMicInputType, 0x48 GetEncoderSelect, 0x26 identify, 0x28 fw/UID, 0x14 meter) - the repo treats opcodes opaquely, naming only 0x29 and only as 'watchdog'; the standard UAC2 SELECTOR UNIT id 15 and the vendor-specific interface 3 (class 0xFF/0xF0, bulk+interrupt) - the repo uses neither; and the full Windows usbaudio2.sys descriptor-defect analysis (duplicate clock-source id, IF3 inside the audio IAD, feature-unit bLength, wTotalLength) - the repo is Linux-only. C4-C7 (forum BIN/XML flashing, 32UC3A4 PCB ID, Ghidra RE, almog v1 0c60:0003 repo) are entirely outside this repo and need their own sources.",
        "urls": [
          {
            "url": "https://github.com/stevebrodie/apogee-one2-linux",
            "what": "Repo landing page (rendered). Confirmed real; description: 'Linux support for the Apogee ONEv2 USB audio interface - kernel patches, vendor init sequence, and keepalive daemon reverse-engineered from scratch'."
          },
          {
            "url": "https://api.github.com/repos/stevebrodie/apogee-one2-linux",
            "what": "API metadata: created_at 2026-05-01T18:41:15Z, pushed_at 2026-05-03, updated_at 2026-08-05, default_branch main, MIT, Python, size 14777 KB, 1 star, topics alsa/apogee/audio/kernel-patch/linux/pipewire/usb-audio."
          },
          {
            "url": "https://api.github.com/repos/stevebrodie/apogee-one2-linux/contents/",
            "what": "File tree: two .patch files, LICENSE, README.md, apogee-init.pcapng (480 B), apogee-one-keepalive.py (5614 B), apogee-one.service (208 B), everything.pcapng.zip (15.5 MB), host.pcapng (434 KB)."
          },
          {
            "url": "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/README.md",
            "what": "README: device 0c60:0017 bcdDevice 1.05; ~9 s watchdog disconnect; 0x29 read every 4 s; recording works, playback fails immediately after open; init captured via Wireshark on macOS (Control2 app); no selector-unit/IF3/input-control mentions."
          },
          {
            "url": "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one-keepalive.py",
            "what": "The keepalive daemon (primary protocol source). Full init sequence + 0x29/6-byte read keepalive at 4 s, bmRequestType 0xc0/0x40, wValue 0, wIndex 0, TIMEOUT 200 ms."
          },
          {
            "url": "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/0001-ALSA-usb-audio-return-true-for-clock-validity-on-query-failure.patch",
            "what": "Kernel patch: sound/usb/clock.c uac_clock_source_is_valid() 'return false' -> 'return true' on failed clock-validity query. Linux analog of the Windows 0xC0440022 clock-validity rejection."
          },
          {
            "url": "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/0002-ALSA-usb-audio-make-media-pad-link-failure-non-fatal.patch",
            "what": "Kernel patch: sound/usb/media.c snd_media_stream_init() 'goto remove_intf_link' -> 'continue' so media_create_pad_link() failure does not block PCM open."
          },
          {
            "url": "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one.service",
            "what": "systemd unit running the keepalive at /usr/local/bin/apogee-one-keepalive.py, Restart=always, RestartSec=2."
          },
          {
            "url": "https://marc.info/?l=alsa-devel&m=164797225004283",
            "what": "alsa-devel 2022-03-22 thread 'Apogee ONEv2 keeps resetting' (0c60:0017 bcdDevice 1.05); OP: resets '~every two seconds', persists with snd-usb-audio disabled; this message is Alan Stern's reply. Repo does not cite it but its watchdog finding plausibly explains it."
          },
          {
            "url": "https://github.com/stefanocoding/take_control",
            "what": "Only related project the README links: control script for Apogee Duet (0c60:0016), described as sharing the ONEv2's vendor command architecture. (Not independently verified in this task.)"
          }
        ]
      },
      {
        "summary": "All seven claims (C1-C7) are supported by primary sources. The headline discovery is independently corroborated and extends our local work: a 2026 Linux project by Steve Brodie (github.com/stevebrodie/apogee-one2-linux) reverse-engineered the ONEv2 vendor init by Wireshark capture on macOS and found the device has a HARDWARE WATCHDOG that disconnects it from USB after ~9 seconds unless the host sends vendor control request 0x29; its daemon sends 0x29 (a 6-byte read) every 4.0 seconds to pet it. This directly explains the 2022 Petr Janecek alsa-devel/linux-usb reset loop (C3) and is the mechanism our local map was missing. Critically for C2: Brodie's keepalive 0x29 (read, 6 bytes) is byte-for-byte the SAME request our Mac-updater disassembly named GetHardwareChanges (read, 6 bytes) - i.e. polling hardware changes doubles as the watchdog reset. The note's phrase '0x29 ~every 9 seconds' conflates two numbers: 9s is the disconnect deadline, the keepalive is actually sent every 4s. The Loopy Pro thread (C4/C5/C6) is thread 47616 'How hard is it to hack (reverse engineer) an audio interface?'; both cited comment IDs 1011044 and 1011073 belong to it. Paa89 edited the updater's XML in Visual Studio to load one of two ONE .BIN files, afterward got Maestro on a USB-C iPad Pro 11 to control input type and +48V but Core Audio still exposed no inputs; MCU identified from PCB photos as 32UC3A4 (= AT32UC3A4, AVR32 UC3A4 - matches our pypcode AVR32-A finding); Ghidra loaded the raw bin and showed functions but RE was never completed, trail ends Nov 2021. C7 confirmed: almog/apogee-one-usb-controller targets ONE v1 (0c60:0003), not v2. BIN filenames/sizes were NOT disclosed on the forum.",
        "verifications": [
          {
            "claim_id": "C1",
            "status": "confirmed",
            "what_the_source_says": "github.com/stevebrodie/apogee-one2-linux (created 2026-05-01, updated 2026-08-05, not a fork, 1 star; topics alsa/apogee/audio/kernel-patch/linux/pipewire/usb-audio). Description verbatim: 'Linux support for the Apogee ONEv2 USB audio interface - kernel patches, vendor init sequence, and keepalive daemon reverse-engineered from scratch'. README: device is 'USB VID:PID 0c60:0017' with 'bcdDevice 1.05'; 'The init sequence was reverse-engineered by capturing USB traffic with Wireshark on macOS while the Apogee Control2 app initialised the device'; the device has 'a hardware watchdog that disconnects the device from USB approximately every 9 seconds unless the host sends a specific vendor USB control command (0x29) to reset it', and the daemon 'sends a 0x29 vendor read every 4 seconds to reset the hardware watchdog'; without it 'the device disconnects from USB every ~9 seconds'. Status: Recording 'Working'; playback PCM opens but 'Stream fails immediately after opening - no audio confirmed yet' / 'Stable audio output has not yet been confirmed'.",
            "reconciliation_with_local": "Matches our VID:PID 0c60:0017 and bcdDevice 1.05 exactly, and our 'recording works, playback incomplete' expectation. ONE CORRECTION to the note: the keepalive request 0x29 is sent every ~4 seconds (both README and the Python script say 4.0s), not every 9 seconds; ~9s is the watchdog DISCONNECT deadline, so the host must pet it well before 9s. This watchdog/keepalive is the piece absent from our local protocol map - our disassembly recovered what 0x29 returns but not that failing to issue it periodically drops the device.",
            "sources": [
              "https://api.github.com/repos/stevebrodie/apogee-one2-linux",
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/README.md",
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one-keepalive.py"
            ]
          },
          {
            "claim_id": "C2",
            "status": "confirmed",
            "what_the_source_says": "Brodie's keepalive is vendor request 0x29, a READ (bmRequestType 0xc0) of 6 bytes, issued every 4.0s from a background thread; the script comment: 'The ONEv2 disconnects from USB after ~9 seconds without this command.' 0x29 also appears twice at the very start of full_init() as a 6-byte read.",
            "reconciliation_with_local": "RECONCILED: our Mac-updater disassembly named 0x29 = GetHardwareChanges, a READ returning 6 bytes. Brodie's keepalive is the identical request (0xc0 read, 6-byte response). So it is the same request, and the keepalive IS a GetHardwareChanges poll - reading the hardware-change status doubles as resetting the watchdog. No contradiction; the two findings corroborate each other (same bRequest, same direction, same 6-byte length).",
            "sources": [
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one-keepalive.py",
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/README.md"
            ]
          },
          {
            "claim_id": "C3",
            "status": "confirmed",
            "what_the_source_says": "The marc.info message (?l=alsa-devel&m=164797225004283) is a reply by Alan Stern dated March 22, 2022. Original reporter Petr Janecek reported the Apogee ONEv2 (idVendor=0c60, idProduct=0017) 'keeps resetting every two seconds or so' in Linux, persisting even with the snd-usb-audio driver disabled (a lower-level USB issue). Stern asked for a usbmon trace and suggested disabling USB runtime PM: 'echo -1 >/sys/module/usbcore/parameters/autosuspend'. Same thread is mirrored on linux-usb (spinics msg224111 report, msg224275 reply).",
            "reconciliation_with_local": "Confirms a real 2022 disconnect/reset loop on the exact device. The 'missing init/keepalive' explanation is strongly supported by Brodie's later watchdog finding (C1/C2). Minor nuance: Janecek observed resets '~every two seconds', while Brodie measured the watchdog deadline at ~9 seconds - the 2s figure may reflect additional enumeration retry behavior or a different measurement point, not a contradiction of the watchdog mechanism.",
            "sources": [
              "https://marc.info/?l=alsa-devel&m=164797225004283",
              "https://www.spinics.net/lists/linux-usb/msg224111.html",
              "https://www.spinics.net/lists/linux-usb/msg224275.html"
            ]
          },
          {
            "claim_id": "C4",
            "status": "confirmed",
            "what_the_source_says": "Loopy Pro thread 47616, single page, posts Oct-Nov 2021. Paa89 (comment 1011776, Nov 2021): 'I was able to let Apogee Maestro on iPad Pro 11 see the Apogee One ... all I did was edit the XML file in the update directory with Visual Studio. I told the Firmware updater to load a different BIN file since there are two bin files for Apogee One in the update directory.' Result: Maestro gained visibility on USB-C iPad Pro and could modify input types and '+48v etc', but 'unfortunately no Audio App sees the Inputs yet.' Also: 'When I connect USB cables that are not from Apogee, Maestro seems to detect the device.'",
            "reconciliation_with_local": "Confirms: two ONE .BIN files plus an editable XML manifest in the updater's update directory; XML edited (in Visual Studio) to point the firmware updater at the alternate BIN; afterward Maestro on a USB-C iPad Pro 11 controlled input type and +48V but Core Audio still exposed no inputs. CAVEAT: the forum never states the two .BIN filenames or their sizes (confirmed 'not disclosed'), and while loading the alternate BIN clearly took effect (Maestro visibility changed), the thread contains no explicit 'flash succeeded/verified' statement beyond the behavioral change. This dovetails with our local dual-bank Image0/Image1 finding (two app images), though we cannot map Paa89's 'two bin files' to Image0/Image1 by name from the forum.",
            "sources": [
              "https://forum.loopypro.com/discussion/47616/how-hard-is-it-to-hack-reverse-engineer-an-audio-interface",
              "https://forum.loopypro.com/discussion/comment/1011044",
              "https://forum.loopypro.com/discussion/comment/1011073"
            ]
          },
          {
            "claim_id": "C5",
            "status": "confirmed",
            "what_the_source_says": "User uncledave identified the MCU from Paa89's PCB photo (comment ~1011053, Oct 2021): 'The 32UC3A4 chip in your photo is the microcontroller', identified as an Atmel processor with a datasheet reference; Paa89 (comment 1011061) thanks him for identifying 'the 32UC3A4 chip' and asks about JTAG.",
            "reconciliation_with_local": "Strong corroboration of our local MCU finding. '32UC3A4' = Atmel/Microchip AT32UC3A4, part of the AVR32 UC3A3/A4 family. Our pypcode (Ghidra AVR32 decoder) disassembly independently proved AVR32-A with reset vector 0x80000000, program_start 0x80004000, 64KB SRAM. The forum's visual identification and our firmware disassembly agree on the exact chip family.",
            "sources": [
              "https://forum.loopypro.com/discussion/47616/how-hard-is-it-to-hack-reverse-engineer-an-audio-interface",
              "https://forum.loopypro.com/discussion/comment/1011073"
            ]
          },
          {
            "claim_id": "C6",
            "status": "confirmed",
            "what_the_source_says": "Paa89 (comment 1012114, Nov 2021): 'I have been unable to view the RAW Bin file with Ghidra. I can see functions etc. hopefully with a bit of Googling I may be able to reverse it one day.' The thread is single-page and the last technical post is this Nov 2021 comment.",
            "reconciliation_with_local": "Confirms Paa89 loaded the raw firmware BIN into Ghidra, could see functions, but did not complete semantic RE; the trail ends ~Nov 2021. Our local work goes substantially further (symbolized request map from the Mac updater, AVR32 confirmation, dual-bank relocation analysis), so Paa89's effort is an earlier, incomplete predecessor, not a source that supersedes ours.",
            "sources": [
              "https://forum.loopypro.com/discussion/47616/how-hard-is-it-to-hack-reverse-engineer-an-audio-interface",
              "https://forum.loopypro.com/discussion/comment/1011073"
            ]
          },
          {
            "claim_id": "C7",
            "status": "confirmed",
            "what_the_source_says": "github.com/almog/apogee-one-usb-controller (created 2026-05-03, no repo description; root has apps/docs/tools dirs, Makefile, README). README describes a tool 'OneMaestro' targeting 'The original Apogee ONE USB interface (v1), identified by USB IDs 0x0c60:0x0003', a macOS utility that controls output level/mute, input source (Int Mic, Ext Mic, Ext 48V Mic, Inst), input gain and direct monitoring while 'keeping Core Audio in charge of audio streaming'. Uses IOUSBHost; references ONEUSB::UpdateLLM() for monitor mix and a legacy 'bRequest=0x06' attenuation path; tested on macOS Tahoe 26.3.1, no binary releases.",
            "reconciliation_with_local": "Confirms the repo is ONE v1 (0c60:0003), NOT the v2 (0c60:0017) we target - its control codes (bRequest 0x06, UpdateLLM) differ from our v2 vendor map and should not be assumed to apply to the v2. It is, however, a useful macOS/IOUSBHost reference for the v1 control model.",
            "sources": [
              "https://api.github.com/repos/almog/apogee-one-usb-controller",
              "https://raw.githubusercontent.com/almog/apogee-one-usb-controller/main/README.md"
            ]
          }
        ],
        "protocol_details": "KEEPALIVE / WATCHDOG (from apogee-one-keepalive.py and README, stevebrodie/apogee-one2-linux): vendor request 0x29, bmRequestType 0xc0 (read), wValue=0, wIndex configurable, response length 6 bytes, control-transfer timeout 200 ms; sent every 4.0 s from a background thread. README: 'a hardware watchdog that disconnects the device from USB approximately every 9 seconds unless the host sends a specific vendor USB control command (0x29) to reset it' and the daemon 'sends a 0x29 vendor read every 4 seconds'. Script comment: 'The ONEv2 disconnects from USB after ~9 seconds without this command.'

INIT SEQUENCE (full_init() in apogee-one-keepalive.py), in order, all bmRequestType 0xc0 read / 0x40 write, wValue=0:
  read 0x29 (6 bytes)
  read 0x31 (4 bytes)
  read 0x29 (6 bytes)
  read 0x1f (1 byte)
  read 0x20 (1 byte)
  read 0x28 (3 bytes)
  read 0x36 (1 byte)
  write 0x34 data=[0x17]
  read 0x44 (1 byte)
  read 0x3e (1 byte)
  read 0x33 (1 byte)
  read 0x35 (1 byte)
  read 0x53 (1 byte)
  write 0x10 data=[0x00]
Script notes: sequence 'was reverse-engineered via Wireshark USB packet capture on macOS'; 'Without it, the device clock is not valid and audio cannot flow.' README attributes the capture to 'the Apogee Control2 app'.

RECONCILIATION WITH OUR SYMBOLIZED MAP: 0x29 read-6 = our GetHardwareChanges (match, incl. 6-byte length). 0x28 read-3 is consistent with our 0x28 = fw version/UID. 0x36 read-1 = GET of our SetMicInputType (we had the 0x40 write form). write 0x34=[0x17] = set mic gain (our 0x34 mic gain; 0x17=23). 0x3e read = our inst gain. 0x53 read = our output route. NEW request codes NOT in our local map: 0x31 (read 4), 0x1f (read 1), 0x20 (read 1), 0x44 (read 1), 0x33 (read 1), 0x35 (read 1), and write 0x10=[0x00] (likely a stream/clock enable). These 7 codes are worth decoding against our firmware disassembly.

ALMOG v1 (different device, 0c60:0003): legacy bRequest=0x06 for attenuation; ONEUSB::UpdateLLM() for direct-monitor mix; accessed via IOUSBHost - do not assume these apply to v2.",
        "bin_xml_details": "From Loopy Pro thread 47616, Paa89 (comment 1011776, Nov 2021): the Apogee updater's 'update directory' contains an XML manifest plus 'two bin files for Apogee One'. Paa89 edited the XML in Visual Studio to instruct the Firmware updater to 'load a different BIN file' (i.e. point it at the second/alternate image). After doing so, Maestro on a USB-C iPad Pro 11 could see the device and set input type and +48V, but 'no Audio App sees the Inputs yet' (Core Audio exposed no input). IMPORTANT GAP: the exact .BIN filenames and their byte sizes, and the exact XML element/field edited, are NOT stated anywhere in the thread (confirmed not disclosed). No manifest checksum/signature discussion appears; Paa89 was able to swap which BIN the updater flashed simply by editing plaintext XML, implying the updater did NOT enforce a manifest integrity/signature check that would block pointing it at an alternate image. This is consistent with our local finding that the two app images (ONEv2_USB_Audio_Image0.bin / Image1.bin) are plaintext and that the trailing 4 bytes 0x00000A94 are identical in both (not a per-image content checksum). We cannot, from the forum, map Paa89's 'two bin files' to our Image0/Image1 by name. Updater self-integrity: no evidence either way that the updater verifies the device-side flash beyond the behavioral change Paa89 observed.",
        "new_vs_known": "GENUINELY NEW (beyond our local work): (1) The HARDWARE WATCHDOG / periodic keepalive requirement - request 0x29 must be issued roughly every 4 s or the device drops off USB within ~9 s. Our disassembly recovered what 0x29 returns (GetHardwareChanges) but not that it is a mandatory liveness ping; this is the single most actionable new fact and the root cause of the Linux reset loop and likely a factor in Windows enumeration. (2) A concrete, ordered init request sequence captured from real macOS traffic, surfacing 7 vendor codes we had not catalogued (0x31, 0x1f, 0x20, 0x44, 0x33, 0x35, and write 0x10=[0x00]). (3) Two working ALSA kernel patches: '0001-ALSA-usb-audio-return-true-for-clock-validity-on-query-failure.patch' and '0002-ALSA-usb-audio-make-media-pad-link-failure-non-fatal.patch' - the clock-validity patch independently corroborates our duplicate-CLOCK_SOURCE-id descriptor defect (the Windows usbaudio2.sys 0xC0440022 noncompliance suspect). (4) Raw USB captures are downloadable for mining: everything.pcapng.zip (15,572,173 bytes), host.pcapng (434,148 bytes), apogee-init.pcapng (480 bytes), plus apogee-one.service and the keepalive daemon. (5) Independent visual MCU ID (32UC3A4) corroborating our pypcode AVR32-A result. (6) Confirmation that the macOS updater's firmware image is selectable via plaintext XML with no blocking integrity check (Paa89).

WHAT OUR LOCAL WORK HAS THAT THESE SOURCES LACK: full SYMBOLIZED semantics of the vendor requests (0x36 SetMicInputType {0/1/2}, 0x34 mic gain, 0x3E inst gain, 0x48 GetEncoderSelect, 0x29 GetHardwareChanges, 0x53 output route, 0x26 identify, 0x28 fw version/UID, 0x14 meter) from Mac updater/ApogeeGlue disassembly - Brodie only has opaque codes from pcap and Paa89 never finished RE; confirmed AVR32-A with exact reset/boot vectors and 64KB SRAM; dual-bank firmware analysis (bank0 @0x80004000, bank1 @0x80024000, 662 diffs all +0x20000 relocations), version 1.5.0, DFU/bootloader in the unshipped first 0x4000; the full USB descriptor dump incl. SELECTOR UNIT id 15 over terminals 9/11/13 and vendor IF3 (class 0xFF/0xF0); and the specific Windows usbaudio2.sys failure 0xC0440022 with candidate descriptor defects (duplicate CLOCK_SOURCE id 1, vendor IF3 inside the audio IAD, feature-unit bLength 10 vs 18, AC wTotalLength 174 vs 167). Net: Brodie's repo is the best external corroboration and adds the keepalive + pcaps + kernel patches; our work remains the authority on request semantics, firmware structure, and the Windows descriptor failure.",
        "urls": [
          {
            "url": "https://github.com/stevebrodie/apogee-one2-linux",
            "what": "C1 primary source: 2026 Linux support project for ONEv2 (0c60:0017) - kernel patches, vendor init sequence, keepalive daemon"
          },
          {
            "url": "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/README.md",
            "what": "Verbatim: 0c60:0017, bcdDevice 1.05, ~9s watchdog disconnect, 0x29 keepalive every 4s, recording works / playback not confirmed, capture via 'Apogee Control2 app'"
          },
          {
            "url": "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one-keepalive.py",
            "what": "C2 primary source: 0x29 read-6 keepalive every 4.0s; full ordered init sequence incl. new codes 0x31/0x1f/0x20/0x44/0x33/0x35 and write 0x10=[0x00]"
          },
          {
            "url": "https://api.github.com/repos/stevebrodie/apogee-one2-linux/contents/",
            "what": "File tree: two ALSA .patch files, keepalive.py, .service, and pcap captures (everything.pcapng.zip 15.5MB, host.pcapng, apogee-init.pcapng) available to mine"
          },
          {
            "url": "https://marc.info/?l=alsa-devel&m=164797225004283",
            "what": "C3: Alan Stern reply (2022-03-22) in the ONEv2 reset-loop thread; device 0c60:0017 'keeps resetting every two seconds'"
          },
          {
            "url": "https://www.spinics.net/lists/linux-usb/msg224111.html",
            "what": "C3: Petr Janecek's original linux-usb report of the ONEv2 reset loop (mirror of the alsa-devel thread)"
          },
          {
            "url": "https://www.spinics.net/lists/linux-usb/msg224275.html",
            "what": "C3: reply in the same ONEv2 reset-loop thread"
          },
          {
            "url": "https://forum.loopypro.com/discussion/47616/how-hard-is-it-to-hack-reverse-engineer-an-audio-interface",
            "what": "C4/C5/C6 primary thread 'How hard is it to hack (reverse engineer) an audio interface?' - Paa89's XML/BIN edit, 32UC3A4 ID, Ghidra attempt"
          },
          {
            "url": "https://forum.loopypro.com/discussion/comment/1011044",
            "what": "C4/C5: one of the two cited comment IDs; redirects into thread 47616 (early comments, Oct 2021)"
          },
          {
            "url": "https://forum.loopypro.com/discussion/comment/1011073",
            "what": "C5/C6: second cited comment ID; redirects into thread 47616. Key later comments: 1011776 (XML/BIN edit), 1011053/1011061 (32UC3A4), 1012114 (Ghidra)"
          },
          {
            "url": "https://github.com/almog/apogee-one-usb-controller",
            "what": "C7: repo (2026-05-03) 'OneMaestro' - a macOS controller for the ONE v1"
          },
          {
            "url": "https://raw.githubusercontent.com/almog/apogee-one-usb-controller/main/README.md",
            "what": "C7 confirmation: targets original ONE v1, USB 0x0c60:0x0003 (NOT v2); uses IOUSBHost, bRequest=0x06, ONEUSB::UpdateLLM()"
          }
        ]
      },
      {
        "summary": "All seven claims (C1-C7) are verified against primary sources. Two findings stand out. (1) stevebrodie/apogee-one2-linux (created 2026-05-01, the only dedicated ONEv2 Linux project on GitHub) independently confirms our v2 request table: its keepalive is literally r(dev, 0x29, 6) = ctrl_transfer(0xC0, 0x29, 0, idx, 6) — i.e. our GetHardwareChanges, a 6-byte vendor READ (bmRequestType 0xC0) — and resetting the hardware watchdog is a side effect of issuing that read. The repo also gives the full init ORDER and a complete Linux bring-up recipe we did not have. (2) stefanocoding/take_control (Apogee Duet, 0c60:0016), cited by stevebrodie as sharing the ONEv2's vendor architecture, is a major external corroboration we had not seen: its request numbers map EXACTLY onto ours — 0x34 mic gain, 0x3E instrument gain, 0x53 output source — using the identical 0x40-write/0xC0-read, wValue=0, 1-byte convention. C7 confirmed: almog/apogee-one-usb-controller targets ONE v1 (0c60:0003), a TAS1020-based design using standard UAC2 selector/feature units plus only two vendor requests (0x02, 0x06) — architecturally unrelated to the AVR32 v2. The Loopy Pro Paa89 thread (Oct-Nov 2021) and Petr Janecek's 2022 alsa/linux-usb report are both confirmed. Key timing nuance: the ~9s figure is the watchdog disconnect interval; the keepalive is actually sent every 4s. One number to re-check: v2 input-type is 0x36 in our first-party decode, but the Duet uses 0x16 for input TYPE (0x36 is its mixer software-return-source) — likely a per-product renumber, and v2's 0x36 is doubly sourced (our Mac-updater decode + stevebrodie's init read), so not a refutation.",
        "verifications": [
          {
            "claim_id": "C1",
            "status": "confirmed",
            "what_the_source_says": "stevebrodie/apogee-one2-linux (GitHub API: created_at 2026-05-01T18:41:15Z, language Python, topics alsa/apogee/audio/kernel-patch/linux/pipewire/usb-audio). README: 'Apogee ONEv2 USB audio interface (USB VID:PID 0c60:0017)', Hardware: 'Apogee ONEv2 (USB VID:PID 0c60:0017, bcdDevice 1.05)'. 'the device requires a proprietary vendor init sequence (discovered via Wireshark USB capture on macOS) before the clock becomes valid'. 'The ONEv2 has a hardware watchdog that disconnects the device from USB approximately every 9 seconds unless the host sends a specific vendor USB control command (0x29) to reset it'. Status table: Capture (recording) = Working; Stable playback audio = 'Stream fails immediately after opening - no audio confirmed yet'. Keepalive sends 0x29 every 4s (code: time.sleep(4.0); README: 'resets the watchdog every 4 seconds').",
            "reconciliation_with_local": "Matches our device identity (0c60:0017, bcdDevice 1.05) and our finding that the proprietary init lives outside the UAC descriptors. PARTIAL nuance on the user's '0x29 ~every 9 seconds': 9s is the DISCONNECT timeout WITHOUT the keepalive; the keepalive 0x29 is actually issued every 4s. 'Recording works, playback incomplete' is exactly confirmed. This is the first external party to reach the same init/watchdog conclusion we reached from the Mac updater.",
            "sources": [
              "https://api.github.com/repos/stevebrodie/apogee-one2-linux",
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/README.md"
            ]
          },
          {
            "claim_id": "C2",
            "status": "confirmed",
            "what_the_source_says": "In apogee-one-keepalive.py the read helper is: def r(dev, req, ln, idx=0): return bytes(dev.ctrl_transfer(0xc0, req, 0, idx, ln, TIMEOUT)). The heartbeat_thread calls r(dev, 0x29, 6) every 4 seconds. Comment: 'The watchdog command (0x29) was isolated by binary search - testing subsets of the init sequence as the heartbeat until the single command that prevented the 9-second disconnect was found.' So 0x29 is a 6-byte vendor READ (bmRequestType 0xC0, wValue 0, wIndex 0).",
            "reconciliation_with_local": "EXACT match to our local note '0x29 = GetHardwareChanges (read, 6 bytes)'. Yes, the keepalive really is 0x29, it is a READ (not a write), of 6 bytes, bmRequestType 0xC0 - identical to our GetHardwareChanges. Resolution: it is the SAME request; the hardware watchdog is reset purely as a side effect of the host performing this 6-byte vendor read. stevebrodie did not know its name (found it by brute-force binary search); our first-party Mac-updater decode supplies the semantic name GetHardwareChanges.",
            "sources": [
              "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one-keepalive.py"
            ]
          },
          {
            "claim_id": "C3",
            "status": "partly",
            "what_the_source_says": "Petr Janecek, linux-usb/alsa-devel, March 2022 (spinics msg224111; marc.info m=164797225004283 is Alan Stern's reply). Device: idVendor=0c60 idProduct=0017, 'ONEv2' by 'Apogee', serial 0C12FF2020204652334D513A7A2A9B, bcdDevice=1.05, kernel v5.16.16. Problem: device 'keeps resetting every two seconds or so', 'even when the snd-usb-audio driver is disabled'. With the driver enabled it emits repeating: 'cannot get min/max values for control 2 (id 10)' / '(id 12)' / '(id 14)'; device connects, ~600-700ms of control errors, then USB disconnect then immediate reconnect. Alan Stern asked for a usbmon trace and to try echo -1 >/sys/module/usbcore/parameters/autosuspend.",
            "reconciliation_with_local": "The error signature 'cannot get min/max values for control 2 (id 10/12/14)' is the UAC2 driver failing to read Volume (control selector 2) ranges from feature units 10/12/14 - exactly the mic-gain feature units that are dead until the proprietary init runs, which is what stevebrodie's clock.c patch + ignore_ctl_error=1 work around. So the root cause (missing proprietary init) is consistent. CAUTION on timing: Petr reports a ~2s reset loop that persists even with snd-usb-audio DISABLED; stevebrodie's watchdog is ~9s. These are two different mechanisms: the ~2s reset is an enumeration/handshake-failure reset (host never completes the vendor handshake), distinct from the ~9s post-init watchdog. 'Explained by missing init/keepalive' is a fair synthesis but conflates the two intervals. The '0xEE string request' mentioned in the task angle was NOT present in any fetched message - no evidence for it.",
            "sources": [
              "https://www.spinics.net/lists/linux-usb/msg224111.html",
              "https://marc.info/?l=alsa-devel&m=164797225004283&w=2",
              "https://www.spinics.net/lists/linux-usb/msg224275.html"
            ]
          },
          {
            "claim_id": "C4",
            "status": "confirmed",
            "what_the_source_says": "Loopy Pro thread 'How hard is it to hack ( reverse engineer) an audio interface?' (discussion 47616), posts Oct-Nov 2021. Paa89: 'I told the Firmware updater to load a different BIN file since there are two bin files for Apogee One in the update directory.' 'all I did was edit the XML file in the update directory with Visual Studio.' Result: 'I was able to let Apogee Maestro on iPad Pro 11 see the Apogee One. I was also able to change the various inputs via Apogee Maestro (+48v etc) but unfortunately no Audio App sees the Inputs yet.' Also: 'When I connect USB cables that are not from Apogee, Maestro seems to detect the device till i disconnect but it doesn't work with Apogees own cable.'",
            "reconciliation_with_local": "Strongly corroborates our dual-bank firmware finding: 'two bin files' == our ONEv2_USB_Audio_Image0.bin / Image1.bin. The editable XML manifest + successful flash of an ALTERNATE bin is independent evidence that the updater performs NO signature/authenticity enforcement on the image it loads (consistent with our 'trailing 4 bytes 0x00000A94 not a content checksum' and no visible integrity gate). Minor date correction: the thread is Oct-Nov 2021, not '2020-2021'. 'USB-C iPad Pro' == 'iPad Pro 11' (USB-C). The +48V-controllable-but-no-Core-Audio-input symptom on iPad mirrors the Windows/Linux pattern (control plane works post-init, data plane does not).",
            "sources": [
              "https://forum.loopypro.com/discussion/47616/how-hard-is-it-to-hack-reverse-engineer-an-audio-interface",
              "https://forum.loopypro.com/discussion/comment/1011044",
              "https://forum.loopypro.com/discussion/comment/1011073"
            ]
          },
          {
            "claim_id": "C5",
            "status": "confirmed",
            "what_the_source_says": "In the same thread (Oct 2021), forum user 'uncledave' wrote: 'The 32UC3A4 chip in your photo is the microcontroller' with a link to the Microchip datasheet. Paa89 supplied the PCB photos.",
            "reconciliation_with_local": "Confirms our pypcode/Ghidra AVR32 finding: the AT32UC3A4 is an Atmel/Microchip AVR32 UC3A4 part, exactly the UC3A3/A4 family we identified from the reset vector and memory map. Attribution nuance: the 32UC3A4 was identified by forum member 'uncledave' from Paa89's photos, not by Paa89 himself (the user's note C5 credits Paa89). Our firmware RE is what actually PROVES the AVR32 ISA; the forum only read the chip marking.",
            "sources": [
              "https://forum.loopypro.com/discussion/comment/1011044",
              "https://forum.loopypro.com/discussion/comment/1011073"
            ]
          },
          {
            "claim_id": "C6",
            "status": "confirmed",
            "what_the_source_says": "Paa89 (Nov 2021): 'I have been unable to view the RAW Bin file with Ghidra. I can see functions etc.' He suggested that with 'a bit of Googling I may be able to reverse it one day', indicating the effort remained incomplete. Thread activity stops at Nov 2021.",
            "reconciliation_with_local": "Confirmed: Paa89 loaded the raw bin into Ghidra and saw functions but never completed semantic RE and never established the ISA programmatically. Our work goes well beyond this (pypcode AVR32 confirmation, reset/program-start trace, dual-bank layout, relocation analysis). Trail stops ~Nov 2021 as stated.",
            "sources": [
              "https://forum.loopypro.com/discussion/comment/1011073"
            ]
          },
          {
            "claim_id": "C7",
            "status": "confirmed",
            "what_the_source_says": "almog/apogee-one-usb-controller (GitHub API: Objective-C, created 2026-05-03, MIT). README: 'This is a working local prototype for the original Apogee ONE USB (0x0c60:0x0003). It has been tested against one connected unit on macOS Tahoe 26.3.1.' Source tools/one-control/main.m: kApogeeVendorID = 0x0c60, kApogeeOneProductID = 0x0003. README: 'The project explicitly addresses only the original Apogee ONE USB (0x0c60:0x0003)'; no v1/v2 designations and no 0017.",
            "reconciliation_with_local": "Confirmed: almog targets ONE v1 (0c60:0003), NOT our v2 (0c60:0017). Critically, v1 is architecturally DIFFERENT: its RE notes name the chip as a TAS1020 (TI 8051-based USB audio MCU, driven via RemoteI2C), whereas our v2 is AVR32 UC3A4. v1 exposes standard UAC2 controls (Selector Unit 7; Feature Units 2/5/9/11/13/22) and uses only TWO vendor requests (0x02 RemoteI2C write, 0x06 LLM output attenuation). This is a fundamentally different control model from v2's extensive vendor-request set. So there is LOW protocol continuity between v1 and v2 (see protocol_details).",
            "sources": [
              "https://api.github.com/repos/almog/apogee-one-usb-controller",
              "https://raw.githubusercontent.com/almog/apogee-one-usb-controller/main/README.md",
              "https://raw.githubusercontent.com/almog/apogee-one-usb-controller/main/docs/legacy-one-reverse-engineering.md"
            ]
          }
        ],
        "protocol_details": "=== ONEv2 (0c60:0017) init + keepalive, verbatim from stevebrodie apogee-one-keepalive.py ===
Transfer helpers: r(dev,req,ln,idx=0) = dev.ctrl_transfer(0xc0, req, 0, idx, ln) [vendor READ]; w(dev,req,data,idx=0) = dev.ctrl_transfer(0x40, req, 0, idx, bytes(data)) [vendor WRITE]. So bmRequestType 0x40(write)/0xC0(read), wValue=0, wIndex=0 (same as our local decode).

full_init(dev) in ORDER (this ORDER is new beyond our table):
  reads: (0x29,6), (0x31,4), (0x29,6), (0x1f,1), (0x20,1), (0x28,3), (0x36,1)
  write: 0x34 <- [0x17]
  reads: (0x44,1), (0x3e,1), (0x33,1), (0x35,1), (0x53,1)
  write: 0x10 <- [0x00]
Keepalive/watchdog: r(dev, 0x29, 6) every 4.0 s (resets the ~9s hardware-disconnect watchdog; 9000+ cycles verified).

Cross-check vs our local v2 table: 0x29=GetHardwareChanges(read6) EXACT; 0x28 read3 = fw version/UID (our note: 3 bytes matches); 0x36 read1 (our SetMicInputType); 0x34 write (our mic gain, written as 0x17=23); 0x3e read (our inst gain); 0x53 read (our output route). NEW requests not in our table: 0x31(read4), 0x1f(read1), 0x20(read1), 0x33(read1), 0x35(read1), 0x44(read1), 0x10(write 0x00).

Linux kernel workarounds (new, actionable): patch1 sound/usb/clock.c uac_clock_source_is_valid(): change 'return false' to 'return true' on clock-validity query failure; patch2 sound/usb/media.c snd_media_stream_init(): change 'goto remove_intf_link' to 'continue' after media_create_pad_link failure; plus options snd_usb_audio ignore_ctl_error=1 and a WirePlumber rule api.alsa.use-acp=false for *ONEv2*. Playback still fails after PCM open ('File descriptor in bad state' / 'No such device or address').

=== Apogee DUET (0c60:0016), verbatim from stefanocoding/take_control take_control.py (NEW corroboration of our v2 architecture) ===
idVendor=0x0c60, idProduct=0x0016; _WRITE=0x40, _READ=0xc0; every read = ctrl_transfer(0xc0, req, 0, wIndex, 1) returning 1 byte; every write = ctrl_transfer(0x40, req, 0, wIndex, [1 byte]). wValue always 0, wIndex = entity/channel index. Request numbers (decimal in source -> hex):
  INPUT: SOFTLIMIT 17=0x11, PHASE 19=0x13, PHANTOM_POWER 21=0x15, TYPE 22=0x16, LEVEL{MIC:52=0x34, INSTRUMENT:62=0x3e}, GROUP 68=0x44
  OUTPUT: LEVEL 51=0x33, MUTE 53=0x35, DIM 64=0x40, SUM_TO_MONO 70=0x46, SOURCE 83=0x53, SPEAKER_OUTPUT_TYPE 182=0xB6
  MIXER: SOFTWARE_RETURN_SOURCE 54=0x36, LEVEL 76=0x4C, PAN 77=0x4D, SOLO 78=0x4E, MUTE 79=0x4F
EXACT semantic matches to our v2 table: mic gain 0x34, instrument gain 0x3e, output source/route 0x53. Also explains v2 init reads 0x33(output level), 0x35(output mute), 0x44(input group). The Duet has NO 0x29, NO init sequence and NO keepalive - README says it 'works great out of the box using ALSA for recording and playing'; the watchdog+init requirement is NEW in the AVR32 ONEv2.
DISCREPANCY to re-check: input-type is Duet 0x16 (TYPE) but our v2 decode says 0x36 (SetMicInputType); on the Duet 0x36 is the mixer SOFTWARE_RETURN_SOURCE. v2's 0x36-as-input-type is independently doubly sourced (our Mac-updater symbol decode + stevebrodie reading 0x36 in the mic phase of init), so most likely a per-product renumber, not an error. Also our tentative 'v2 0x21 phantom?' is unsupported here - the Duet phantom is 0x15, and on the single-input ONE 48V is most likely folded into SetMicInputType value 2 (Ext48V) rather than a separate request. Flag 0x21 as unverified.

=== ONE v1 (0c60:0003), from almog docs/legacy-one-reverse-engineering.md (DIFFERENT architecture) ===
v1 is TAS1020-based and uses STANDARD UAC2 class controls for most functions: input select via Selector Unit 7 (pins 1->FU5 Int Mic, 2->FU11 Ext Mic, 3->FU13 Ext 48V Mic, 4->FU9 Inst); gains via Feature Units 5/9/11/13; main out FU2; headphone FU22. Only TWO vendor requests: (a) ONEUSB::SetLLMOutAtt -> bmRequestType 0x40, bRequest 0x06, wValue = -atten_db (signed16), wIndex 0, wLength 0; (b) TAS1020 RemoteI2C monitor-mix -> bmRequestType 0x40, bRequest 0x02, wValue 0x2b50, wIndex = ext_mic_level, wLength 1, payload byte (0x40 | inst_or_int_mic_level), values inverted 0=loud..63=silent. one-control.m sends standard UAC with wValue=(control_selector<<8)|channel, wIndex=(entity_id<<8)|AudioControlInterface. CONCLUSION: v1 (TAS1020, standard-UAC + 2 vendor reqs) and v2 (AVR32, large vendor-req set + watchdog) are NOT a continuous protocol; the real lineage is Duet(0016)->ONEv2(0017), not ONEv1(0003)->ONEv2(0017).",
        "bin_xml_details": "Loopy Pro user Paa89 (thread 47616, Oct-Nov 2021) independently corroborates our dual-bank firmware structure. Verbatim: 'I told the Firmware updater to load a different BIN file since there are two bin files for Apogee One in the update directory' and 'all I did was edit the XML file in the update directory with Visual Studio.' This matches our two images (ONEv2_USB_Audio_Image0.bin / Image1.bin). The fact that he edited a plaintext XML manifest to redirect the updater to an ALTERNATE bin and the device accepted and ran it is independent evidence that the updater enforces NO signature/authenticity check on the selected image - consistent with our finding that the trailing 4 bytes (0x00000A94, identical in both images) are not a content checksum and that images are plaintext. MCU per the thread: AT32UC3A4 (identified by member 'uncledave', Oct 2021) = our AVR32 UC3A3/A4 family. Limits of the external source: no detail on the XML manifest's fields/schema, no per-bin address/bank mapping, no checksum/CRC field names - our local work supplies all of that (bank0 @0x80004000, bank1 @0x80024000, 662 diffs all +0x20000 relocations, DFU in the unshipped first 0x4000 bootloader region). Neither stevebrodie nor the ALSA thread touch firmware/bin/XML at all. No source anywhere describes the updater's integrity-checking logic; the only data point is Paa89's successful unsigned re-flash, which argues the check is weak or absent.",
        "new_vs_known": "GENUINELY NEW (not in our local notes):
1. take_control (Apogee Duet 0c60:0016) full vendor request map - a THIRD device in the same family that independently validates our v2 convention (0x40/0xc0, wValue=0, 1 byte) and specific numbers: 0x34 mic gain, 0x3e inst gain, 0x53 output source are EXACT; 0x33/0x35/0x44 appear in both. This is the strongest external corroboration of our v2 decode and establishes the Duet->ONEv2 protocol lineage. We did not have this before.
2. The ONEv2 init SEQUENCE ORDER (stevebrodie full_init): we had the request table but not the ordered handshake. New/unseen request numbers in it: 0x31(r4), 0x1f(r1), 0x20(r1), 0x33(r1), 0x35(r1), 0x44(r1), and a write 0x10<-0x00. The 0x34 gain is written as 0x17 (=23) during init.
3. Watchdog operational facts: ~9s disconnect timeout, keepalive = the 0x29 6-byte read issued every 4s, 9000+ cycles stable; watchdog reset is a side effect of the read.
4. A complete Linux bring-up recipe: two one-line kernel patches (clock.c return true; media.c continue), ignore_ctl_error=1, WirePlumber use-acp=false, systemd keepalive service - plus the honest limitation that playback still fails after PCM open.
5. ALSA exact failure signature + environment: 'cannot get min/max values for control 2 (id 10/12/14)', ~2s reset loop even with driver disabled, kernel 5.16.16, serial 0C12FF2020204652334D513A7A2A9B.
6. Loopy Pro: independent confirmation of two bins + editable XML manifest + successful UNSIGNED alternate-bin flash + 32UC3A4.

WHAT OUR LOCAL WORK HAS THAT THESE SOURCES LACK:
1. First-party SEMANTIC naming of the vendor requests from Apogee's own symbolized Mac updater (SetMicInputType 0x36 {0=Int,1=Ext,2=Ext48V}, GetHardwareChanges 0x29, GetEncoderSelect 0x48, meter 0x14, identify 0x26, fw/UID 0x28, inst gain 0x3e, output 0x53). stevebrodie treats 0x29 as an opaque watchdog found by brute force; take_control is a different device. No external source names any ONEv2 request.
2. Full firmware RE: programmatic AVR32 ISA proof (pypcode), reset vector 0x80000000->program_start 0x80004000->_stext 0x80006950 (SP=0x10000/64KB SRAM), dual-bank layout and +0x20000 relocation proof, DFU in the unshipped bootloader region, version mapping 1.5.0=1.05. Paa89 only saw 'functions' in Ghidra; stevebrodie did zero firmware RE.
3. Windows story entirely: usbaudio2.sys FAILS_START 0xC0440022 (Event ID 34) and the specific candidate descriptor defects (duplicate CLOCK_SOURCE id1, vendor IF3 inside the audio IAD, feature-unit bLength 10 vs 18, AC wTotalLength 174 vs 167). No external source mentions Windows.
4. Full UAC2 descriptor dump incl. Selector Unit 15 over mic terminals 9/11/13 and vendor IF3 (0xFF/0xF0, bulk+interrupt).

DISCREPANCIES / RE-CHECK ITEMS:
- Input-type request: ours=0x36, Duet=0x16 (Duet 0x36=mixer software-return-source). v2 0x36 is doubly sourced so likely a per-product renumber, but worth a 1-line re-confirm in our disassembly.
- 'v2 0x21 phantom?' is unsupported: Duet phantom=0x15; on the single-input ONE, 48V is likely value 2 of SetMicInputType (Ext48V), not a separate request. Treat 0x21 as unverified.
- '0xEE string request' from the task angle: no evidence in any fetched ALSA message.
- NO other ONEv2 RE work exists beyond these four sources (GitHub topic 'apogee' lists only stevebrodie + matt8707/duet2-startup which is just Duet-2 automation; the 2026/05 LKML 'iface reset quirk' patch is for TAE1159 25aa:600b, unrelated).",
        "urls": [
          {
            "url": "https://github.com/stevebrodie/apogee-one2-linux",
            "what": "C1/C2/C3 primary: the 2026 ONEv2 Linux project (0c60:0017, bcdDevice 1.05); init sequence, keepalive, kernel patches"
          },
          {
            "url": "https://api.github.com/repos/stevebrodie/apogee-one2-linux",
            "what": "Metadata: created 2026-05-01, Python, topics alsa/apogee/usb-audio"
          },
          {
            "url": "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/README.md",
            "what": "Full README: watchdog ~9s, keepalive 0x29 every 4s, clock.c/media.c patches, playback-incomplete status, take_control cross-reference"
          },
          {
            "url": "https://raw.githubusercontent.com/stevebrodie/apogee-one2-linux/main/apogee-one-keepalive.py",
            "what": "C2 proof: r(dev,0x29,6)=ctrl_transfer(0xc0,0x29,0,idx,6); full_init() order; 4s heartbeat"
          },
          {
            "url": "https://github.com/almog/apogee-one-usb-controller",
            "what": "C7 primary: targets ONE v1 (0c60:0003), not v2"
          },
          {
            "url": "https://api.github.com/repos/almog/apogee-one-usb-controller",
            "what": "Metadata: Objective-C, created 2026-05-03, MIT"
          },
          {
            "url": "https://raw.githubusercontent.com/almog/apogee-one-usb-controller/main/README.md",
            "what": "States it targets original ONE 0x0c60:0x0003 only; macOS Tahoe 26.3.1"
          },
          {
            "url": "https://raw.githubusercontent.com/almog/apogee-one-usb-controller/main/docs/legacy-one-reverse-engineering.md",
            "what": "v1 protocol: TAS1020, Selector Unit 7 + Feature Units, vendor 0x06 (LLM atten) and 0x02 (RemoteI2C monitor mix) with exact fields"
          },
          {
            "url": "https://raw.githubusercontent.com/almog/apogee-one-usb-controller/main/tools/one-control/main.m",
            "what": "v1 source: kApogeeVendorID=0x0c60, kApogeeOneProductID=0x0003, UAC request construction"
          },
          {
            "url": "https://github.com/stefanocoding/take_control",
            "what": "NEW lead: Apogee Duet (0c60:0016) Linux control; same vendor architecture as ONEv2"
          },
          {
            "url": "https://api.github.com/repos/stefanocoding/take_control",
            "what": "Metadata: 'Take control of your Apogee Duet on Linux!', Python, created 2019, last push 2023-04-21, 22 stars"
          },
          {
            "url": "https://raw.githubusercontent.com/stefanocoding/take_control/master/take_control.py",
            "what": "Duet request map (dec->hex): mic gain 0x34, inst gain 0x3e, output source 0x53, input type 0x16, phantom 0x15, etc.; 0x40/0xc0, wValue=0, 1 byte"
          },
          {
            "url": "https://www.spinics.net/lists/linux-usb/msg224111.html",
            "what": "C3 primary: Petr Janecek original report; dmesg 'cannot get min/max values for control 2 (id 10/12/14)', ~2s reset, serial, bcdDevice 1.05, kernel 5.16.16"
          },
          {
            "url": "https://marc.info/?l=alsa-devel&m=164797225004283&w=2",
            "what": "C3: Alan Stern reply (March 2022) requesting usbmon trace; same thread"
          },
          {
            "url": "https://www.spinics.net/lists/linux-usb/msg224275.html",
            "what": "C3: related reply in the resetting thread"
          },
          {
            "url": "https://forum.loopypro.com/discussion/47616/how-hard-is-it-to-hack-reverse-engineer-an-audio-interface",
            "what": "C4/C5/C6 canonical thread 'How hard is it to hack (reverse engineer) an audio interface?', Oct-Nov 2021"
          },
          {
            "url": "https://forum.loopypro.com/discussion/comment/1011044",
            "what": "C4/C5: Paa89 two bins + XML edit + iPad Pro 11 result; uncledave identifies 32UC3A4"
          },
          {
            "url": "https://forum.loopypro.com/discussion/comment/1011073",
            "what": "C6: Paa89 'unable to view the RAW Bin file with Ghidra. I can see functions etc.' - RE incomplete"
          },
          {
            "url": "https://github.com/topics/apogee",
            "what": "Confirms no other ONEv2 RE repos (only stevebrodie + matt8707/duet2-startup automation)"
          },
          {
            "url": "https://ratatoskr.run/lkml/2026/05/17034279/t",
            "what": "False lead ruled out: 2026/05 ALSA 'iface reset quirk' patch is for TAE1159 25aa:600b, not Apogee"
          }
        ]
      }
    ]
  },
  "workflowProgress": [
    {
      "type": "workflow_phase",
      "index": 1,
      "title": "Fetch"
    },
    {
      "type": "workflow_phase",
      "index": 2,
      "title": "Synthesize"
    },
    {
      "type": "workflow_agent",
      "index": 1,
      "label": "fetch:brodie_repo",
      "phaseIndex": 1,
      "phaseTitle": "Fetch",
      "agentId": "a450dc55e5ce15e88",
      "model": "claude-opus-4-8",
      "state": "done",
      "startedAt": 1790833316263,
      "queuedAt": 1790833316244,
      "attempt": 1,
      "lastToolName": "StructuredOutput",
      "lastToolSummary": "Examined github.com/stevebrodie/apogee-one2-linux in depth …",
      "promptPreview": "OUR LOCAL, FIRST-PARTY FINDINGS (authoritative, from disassembling Apogee's own Mac updater + dumping the device + pypcode disassembly of the firmware):
- Device: Apogee ONE v2, USB 0c60:0017, product "ONEv2", bcdDevice 1.05. USB descriptors dumped from the actual unit: UAC2 composite; AudioControl interface has a standard read/write SELECTOR UNIT id 15 over three Microphone input terminals (9/11/…",
      "promptFramed": true,
      "lastProgressAt": 1790833574408,
      "tokens": 67958,
      "toolCalls": 12,
      "durationMs": 258141,
      "resultPreview": "{"summary":"Examined github.com/stevebrodie/apogee-one2-linux in depth (API metadata, README, the keepalive daemon source, both kernel patches, the systemd unit). The repo is REAL and first-party reverse-engineering work: created 2026-05-01, pushed 2026-05-03, updated 2026-08-05, default branch main, MIT, Python, ~14.8 MB (mostly a 15.5 MB everything.pcapng.zip USB capture). It targets exactly our…"
    },
    {
      "type": "workflow_agent",
      "index": 2,
      "label": "fetch:forum_paa89",
      "phaseIndex": 1,
      "phaseTitle": "Fetch",
      "agentId": "a3852374574d31b05",
      "model": "claude-opus-4-8",
      "state": "done",
      "startedAt": 1790833316265,
      "queuedAt": 1790833316245,
      "attempt": 1,
      "lastToolName": "StructuredOutput",
      "lastToolSummary": "All seven claims (C1-C7) are supported by primary sources. …",
      "promptPreview": "OUR LOCAL, FIRST-PARTY FINDINGS (authoritative, from disassembling Apogee's own Mac updater + dumping the device + pypcode disassembly of the firmware):
- Device: Apogee ONE v2, USB 0c60:0017, product "ONEv2", bcdDevice 1.05. USB descriptors dumped from the actual unit: UAC2 composite; AudioControl interface has a standard read/write SELECTOR UNIT id 15 over three Microphone input terminals (9/11/…",
      "promptFramed": true,
      "lastProgressAt": 1790833691878,
      "tokens": 82965,
      "toolCalls": 16,
      "durationMs": 373704,
      "resultPreview": "{"summary":"All seven claims (C1-C7) are supported by primary sources. The headline discovery is independently corroborated and extends our local work: a 2026 Linux project by Steve Brodie (github.com/stevebrodie/apogee-one2-linux) reverse-engineered the ONEv2 vendor init by Wireshark capture on macOS and found the device has a HARDWARE WATCHDOG that disconnects it from USB after ~9 seconds unless…"
    },
    {
      "type": "workflow_agent",
      "index": 3,
      "label": "fetch:v1_and_alsa",
      "phaseIndex": 1,
      "phaseTitle": "Fetch",
      "agentId": "a8a4adbac4ed1b45e",
      "model": "claude-opus-4-8",
      "state": "done",
      "startedAt": 1790833316266,
      "queuedAt": 1790833316245,
      "attempt": 1,
      "lastToolName": "StructuredOutput",
      "lastToolSummary": "All seven claims (C1-C7) are verified against primary sourc…",
      "promptPreview": "OUR LOCAL, FIRST-PARTY FINDINGS (authoritative, from disassembling Apogee's own Mac updater + dumping the device + pypcode disassembly of the firmware):
- Device: Apogee ONE v2, USB 0c60:0017, product "ONEv2", bcdDevice 1.05. USB descriptors dumped from the actual unit: UAC2 composite; AudioControl interface has a standard read/write SELECTOR UNIT id 15 over three Microphone input terminals (9/11/…",
      "promptFramed": true,
      "lastProgressAt": 1790833825669,
      "tokens": 105036,
      "toolCalls": 32,
      "durationMs": 507494,
      "resultPreview": "{"summary":"All seven claims (C1-C7) are verified against primary sources. Two findings stand out. (1) stevebrodie/apogee-one2-linux (created 2026-05-01, the only dedicated ONEv2 Linux project on GitHub) independently confirms our v2 request table: its keepalive is literally r(dev, 0x29, 6) = ctrl_transfer(0xC0, 0x29, 0, idx, 6) — i.e. our GetHardwareChanges, a 6-byte vendor READ (bmRequestType 0x…"
    },
    {
      "type": "workflow_agent",
      "index": 4,
      "label": "synthesize",
      "phaseIndex": 2,
      "phaseTitle": "Synthesize",
      "agentId": "a28b1133fd0e9d728",
      "model": "claude-opus-4-8",
      "state": "done",
      "startedAt": 1790833827803,
      "queuedAt": 1790833827800,
      "attempt": 1,
      "lastToolName": "Bash",
      "lastToolSummary": "ls -la "<project>/resources/" 2>/dev/null; echo…",
      "promptPreview": "OUR LOCAL, FIRST-PARTY FINDINGS (authoritative, from disassembling Apogee's own Mac updater + dumping the device + pypcode disassembly of the firmware):
- Device: Apogee ONE v2, USB 0c60:0017, product "ONEv2", bcdDevice 1.05. USB descriptors dumped from the actual unit: UAC2 composite; AudioControl interface has a standard read/write SELECTOR UNIT id 15 over three Microphone input terminals (9/11/…",
      "promptFramed": true,
      "lastProgressAt": 1790834136902,
      "tokens": 86292,
      "toolCalls": 3,
      "durationMs": 309099,
      "resultPreview": "I have all the context I need. The memory, the two existing reports, and the three verification passes in the JSON all line up. I'll now synthesize the Korean verification note, reconciling the three passes and flagging their internal discrepancies honestly.

Here is the note:

---

# 외부 노트 검증 결과 — Apogee ONE v2 (0c60:0017)

> 이 문서는 사용자가 가져온 외부 연구 노트(주장 C1–C7)를 **1차 소스**에 대조해 검증한 결과다. 검증 데이터는 리서치 …"
    }
  ],
  "totalTokens": 342251,
  "totalToolCalls": 63
}