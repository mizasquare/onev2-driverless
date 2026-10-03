# MFi/iAP와 워치독·USB-C 호환

> 대상: Apogee ONE v2 ("ONE for iPad & Mac", 2013, USB 0c60:0017)
> 작성 근거: 우리 펌웨어 디스어셈블(Ghidra/pypcode, AVR32 UC3A4) + 공개 문서/특허 + 포럼·벤더 보고
> 등급 표기: **[확인]** 우리 RE나 1차 자료로 검증 · **[널리보고됨]** 사용자/포럼 다수 보고 · **[추정]** 근거 있는 추론(코드에 의도 명시는 없음)

---

## 한 줄 요약

- "주기적으로 안 건드리면 끊는" 동작은 **공개 MFi 규약에 적힌 조항이 아니라, iAP 세션 모델(호스트가 계속 세션을 몰아준다는 전제)을 흉내 낸 Apogee 설계**일 가능성이 가장 높다. **[추정]** 다만 네가 떠올린 "세션 유지 안 하면 끊는다"는 **큰 그림 자체는 iAP의 실제 성질과 맞다.** **[확인]**
- 중요한 사실 정정: 이 펌웨어가 돌리는 건 외부 리서치가 말한 **iAP2가 아니라 iAP1**이다(우리 디스어셈블로 확인). 2013년 "iPad & Mac"용 기기라 iAP1이 자연스럽다. **[확인]**
- **USB-C 전환이 입력을 못 잡게 만든 날짜**: iPad USB-C는 2018-10-30 발표(2018-11 출하), iPhone은 iPhone 15로 2023-09-12 발표(2023-09-22 출시). 이 전환으로 레거시 MFi/iAP 액세서리 제어 경로가 iOS에서 사라졌다. **[확인]**
- **네 시나리오의 핵심 반전**: stock iOS에서는 출력(재생)이 되므로 기기는 **재열거(디스커넥트)되고 있지 않다 → 워치독이 실제 범인이 아닐 가능성이 크다.** 진짜 문제는 "입력이 어떤 앱에도 등록 안 됨"(MFi 제어 경로 상실)이다. **[널리보고됨 + 추정]**

---

## 질문 1 — MFi/iAP가 "주기적으로 상태 읽힐 준비 하고 안 읽히면 끊어라"를 규약으로 요구했나? (2015 언저리 포함)

**직답: 공개 문서에는 그런 "N초마다 폴링 안 하면 자동 리셋" 조항이 없다. 하지만 iAP는 본질적으로 세션/타임아웃 기반 링크라서, 네 추측의 "방향"은 맞다.**

- **공개로 확인되는 것 [확인]**
  - iAP(및 후속 iAP2)는 fire-and-forget가 아니라 **호스트(아이폰/아이패드)가 끌고 가는 세션**이다. 인증(MFi 인증 코프로세서 챌린지-리스폰스) → 식별(identify) → 운용 순서를 거치고, 링크 계층이 ACK/재전송/시퀀싱과 **협상된 타임아웃**으로 동작한다.
  - Apple 자체 특허 **US9306879B2**(1차 자료)가 **식별이 타임아웃 구동**임을 명시한다: 호스트가 IDStart를 보냈는데 액세서리가 제때 IDInfo로 답하지 않으면 호스트가 IDTimeout을 보내고, **"액세서리가 연결을 다시 수립(reestablish)"** 해서 식별을 재시작할 수 있다. 예시 타임아웃으로 100ms, 2s 등이 언급된다. → **"호스트가 세션을 안 몰아주면 액세서리가 링크를 스스로 다시 세운다(=재열거)"** 라는, ONE의 ~9초 재열거와 **같은 모양**의 동작이 부분적으로 문서화돼 있다.
- **NDA라서 확정도 반증도 못 하는 것**
  - iAP2의 keepalive/타임아웃 숫자나 "유휴 시 끊어라" 같은 구체 조항은 **MFi Accessory Interface Specification(NDA)** 안에만 있을 수 있어 공개 확인 불가. 독립 iAP2 구현(iap2-rs)과 리버스 문서(wiomoc)에도 **유휴 타임아웃/하트비트/필수 주기 메시지는 드러나 있지 않다.** 따라서 "2015년 언저리 그런 조항이 있었다"를 **사실로 단정할 수 없다**(없다고도 단정 불가).
  - 시기 관련: Lightning+iAP2는 2012-09에 등장해 2013~2016 창에서 현역이었으니 "2015 언저리"라는 네 기억의 시기 감각은 맞다. 다만 **이 기기는 iAP1**이라 더 고전적인 계열이다. **[확인]**
- **우리 기기에서 확인되는 것 [확인]**
  - 펌웨어에 실제 iAP 세션 머신이 있다: `FUN_8000f8fc`가 iAP1 틱 핸들러로 시작바이트 **0x55**, lingo **0x38**, 체크섬 `-(sum)` = 전형적 **iAP1 프레이밍**(iAP2의 0xFF5A 아님). 재전송 500틱×10회("packet timed out... resending"), 세션 리로드 카운터 10000. → 외부 리서치의 "iAP2 스택" 표현은 **기기 수준에서 부정확**; 실제는 iAP1.

**결론(Q1):** "주기적 세션 유지가 끊기면 링크가 리셋된다"는 성질은 **iAP의 실제 동작으로 확인**된다. 그러나 "USB 오디오 액세서리는 N초마다 폴링돼야 한다"는 **문자 그대로의 공개 조항은 없다.** 네 추측은 규약 인용이 아니라 **iAP 세션 모델에 대한 올바른 직관**으로 봐야 한다.

---

## 질문 2 — USB-C 아이폰/아이패드 전환이 왜 이 기기 입력을 못 잡게 만들었나 (날짜 포함)

**직답: ONE은 Lightning 시절 iAP/MFi로 제어되던 "App-Enabled MFi 액세서리"인데, USB-C iOS에는 그 MFi/iAP 제어 경로가 없어서 입력 설정/등록이 깨진다. 오디오 클래스(UAC) 재생만 남는다.**

- **타임라인 [확인]**
  - 2012-09-12 Lightning + iAP 등장 → **2013 ONE**가 Lightning iPad + Mac용으로 설계 → **2018-10-30 첫 USB-C iPad Pro 발표(2018-11 출하)** → **2023-09-12 iPhone 15 발표, 2023-09-22 출시(첫 USB-C 아이폰).** 이 구간에서 레거시 MFi 액세서리 경로가 iOS에서 사라졌다.
- **벤더 공식 입장 [확인] (Apogee KB, 1차)**
  - "Apple does not offer MFi certification for the new USB-C iPad Pro models", "no path to compatibility has emerged." ONE에 대해선 verbatim으로 **"Inputs do not register in any app"**, 대신 **"Output control, playback, streaming... works."**
- **사용자/포럼 보고 [널리보고됨]**
  - USB-C iPad에서 재생은 되지만 Maestro로 팬텀/게인/입력을 못 바꾼다. 애플 커뮤니티에선 Apogee 지원이 "the issue is with Apple not supporting MFi on USB-C devices"라고 전한 보고. Mac과 Lightning iPhone(XR)에선 정상.
  - 추가 악재 [널리보고됨/추정]: Apogee KB는 iOS 26에선 **Lightning 기기(iPhone 14)에서도** ONEv2 입력이 안 된다고 안내(출력은 됨), 녹음 필요 시 iOS 18 이하 유지 권고. iPadOS 26의 시스템 전역 입력 선택 개편과의 인과는 추정.

**결론(Q2):** USB-C 전환은 "USB 전기 신호"가 아니라 **iOS가 더 이상 레거시 MFi/iAP 제어 세션을 이 기기에 열어주지 않는다**는 점에서 입력을 죽인다. 범용 클래스컴플라이언트 UAC2 인터페이스는 iAP가 필요 없어 멀쩡히 되는데, ONE은 입력 구성에 iAP를 쓰기 때문에 유독 최악이 된다.

---

## 질문 3 — 이 기기의 ~9초 디스커넥트: MFi 요구인가, Apogee 설계인가? (현재 판단)

**현재 판단: Apogee 설계 쪽. 단, iAP/MFi의 "호스트가 능동 세션을 유지한다"는 모델을 반영/흉내 낸 설계. (근거 있는 추정, 중간 신뢰도)**

- **[확인] (우리 디스어셈블)**
  - 0x29 핸들러(`FUN_800093d4`의 ')' case)는 **순수 6바이트 상태 리더**로, 워치독을 쓰다듬는 코드가 **없다.** 하위 getter들(변경 플래그 0x2538 읽고 클리어, 현재 선택, 샘플레이트)만 호출.
  - → **~9초 워치독은 0x29 의미와 무관하게, "아무 EP0 컨트롤 요청이든 처리하는 행위" 자체로 하위 계층에서 리셋된다.** stevebrodie의 Linux 프로젝트가 0x29를 쓰는 건 단지 "항상 성공하는 읽기"라서지 0x29가 특별해서가 아니다.
  - Linux에서 유휴 시 ~9초 재열거, 4.0초 하트비트로 생존은 **재현/문서화됨 [확인]**.
- **[추정] (코드에 의도 명시 없음)**
  - 펌웨어가 진짜 iAP(iAP1) 세션 머신을 품고 있으므로, **"능동 호스트 제어 세션이 없으면 클린 상태로 리셋/복구"** 하려는 설계가 가장 그럴듯. 즉 Apple 규약 조항의 직역이 아니라 **iAP 세션 전제에서 파생된 Apogee 구현 선택**.
  - 정확한 detach 타이머/ISR 명령은 아직 못 집었다(EVBA 0x80016C00 벡터테이블 + 타이머 주변장치 파싱 필요). 그래서 "의도=iAP"는 **증명이 아니라 가설**.

**두 계층을 분리해서 기억:** (a) iAP 식별/링크 타임아웃 = **문서화된 Apple 프로토콜**; (b) ONE의 EP0-유휴 워치독 = **Apogee 펌웨어**(아마 a에서 파생).

---

## 보너스 — 맥에선 왜 Apogee 앱 없이도 잘 됐나?

- **[확인]** 오디오 경로는 표준 **UAC2**이고 macOS는 10.6.4(2010)부터 클래스드라이버로 네이티브 지원. Apogee의 Mac kext(`ONEv2USBOverideDriver.kext`)는 **코드 없는 override**(레이턴시/이름만) → 실제 오디오는 Apple 클래스 드라이버가 처리. 셀렉터 유닛 id 15가 Int/Ext 입력을 CoreAudio 소스로 노출.
- **[추정]** Core Audio가 기기를 계속 능동적으로 물고 있어(클럭/볼륨/스트림 컨트롤 트래픽) **EP0 워치독이 자연히 먹여진다.** 반면 bare Linux의 snd-usb-audio는 초기 1회 설정 후 아이소크로너스만 흘려 EP0을 안 건드려서 ~9초에 굶어 죽는다.
- **[추정]** 또한 Mac은 iAP/iOS 호스트가 아니라 **일반 USB 호스트**라, iAP 세션 타임아웃/리셋 경로 자체가 발동하지 않는다. Lightning iOS에선 iAP 세션이 유지됐고, USB-C iOS에선 그 핸드셰이크가 더 이상 같은 방식으로 일어나지 않아 입력이 등록 안 된다.

---

## 근거 등급 구분 (공개문서 / NDA / 추론)

| 주장 | 등급 | 출처 성격 |
|---|---|---|
| iAP는 세션/타임아웃 기반, 식별 타임아웃 시 액세서리가 링크 재수립 | [확인] | 공개(Apple 특허 US9306879B2) + 리버스 문서 |
| "N초 폴링 안 하면 자동 리셋" 같은 USB-오디오 전용 조항 | 공개엔 없음 / NDA 영역 | 공개 부재 + MFi 스펙 NDA |
| 이 펌웨어는 iAP1(0x55/lingo0x38/-(sum)) | [확인] | 우리 디스어셈블 |
| ~9초 워치독은 아무 EP0 요청으로 리셋(0x29 특별 아님) | [확인] | 우리 디스어셈블 + Linux 재현 |
| 워치독 의도 = iAP 세션 전제 반영한 Apogee 설계 | [추정] | 코드에 의도 명시 없음 |
| USB-C iPad/iPhone에서 입력 미등록, 출력만 됨 | [확인] | Apogee KB(벤더 1차) |
| 원인 = USB-C iOS에 MFi/iAP 제어 경로 없음 | [확인/널리보고됨] | 벤더 KB + 포럼 |
| USB-C 전환 날짜(2018 iPad / 2023 iPhone) | [확인] | 공개 보도 |
| macOS UAC2 네이티브(10.6.4)로 앱 없이 동작 | [확인] | 공개 + 우리 kext 분석 |
| Core Audio가 워치독을 먹인다 / Mac은 iAP 경로 미발동 | [추정] | 근거 있는 추론 |
| iOS엔 유저스페이스 raw USB 없음(피더/커스텀 호스트 불가) | [확인] | Apple 개발자 문서 |

---

## 네 시나리오(USB-C 아이폰/아이패드)에 대한 실질적 함의

- stock iOS에서 **출력이 된다 = 기기가 재열거되지 않는다 → 워치독은 거기서 실제 블로커가 아닐 공산이 크다.** 진짜 벽은 "MFi/iAP 제어 경로 상실로 입력 미등록"이다. **[추정, 출력 동작은 널리보고됨]**
- 그런데 네 걱정도 이중으로 타당하다: iOS엔 libusb/raw EP0/IOKit HID가 없고 External Accessory는 MFi 라이선스 전용이라, **(1) 워치독을 먹이는 피더(우리 Layer B)도, (2) 입력을 되살리는 커스텀 제어도 호스트 쪽에서 불가능.** Mac/PC와 달리 USB-C iOS는 **호스트 측 구제가 원천 봉쇄**.
- 따라서 잠긴 iOS 호스트에 유효한 건 **기기 측(Strategy C, 펌웨어)** 뿐이다: 워치독 제거/연장 패치. 다만 입력 미등록(iAP 상실)까지 이걸로 해결되는지는 별개 문제이고, **어떤 펌웨어 작업도 JTAG 풀백업이 선행**돼야 한다(부트로더/DFU 영역 0x80000000–0x80003FFF는 업데이트 파일에 없음).

---

## 참고 링크

**1차/공개 문서**
- Apple 특허 US9306879B2 — iAP 식별 타임아웃, IDTimeout 후 액세서리 연결 재수립: https://patents.google.com/patent/US9306879B2/en
- Apogee KB (USB-C iPad/iPhone 호환, iOS 26 포함): https://knowledge.apogeedigital.com/do-apogee-products-work-with-the-ipad-pro-with-usb-c-port
- Apple External Accessory (인증·세션 게이트): https://developer.apple.com/library/ios/featuredarticles/ExternalAccessoryPT/Articles/MonitoringEvents.html
- Apple Platform Security — MFi 인증 코프로세서: https://support.apple.com/guide/security/verifying-accessories-sec70a4f377d/web
- macOS UAC2 네이티브(10.6.4): https://www.xmos.com/software/usb-audio/driver-support/
- iOS raw USB 불가 / DriverKit 제약: https://developer.apple.com/forums/thread/743878

**iAP 리버스 문서 (NDA 아님, 비공식)**
- wiomoc iAP/iAP2 리버스 글: https://wiomoc.de/misc/posts/mfi_iap.html
- iap2-rs(오픈 iAP2 구현): https://github.com/usenocturne/iap2-rs

**기기별 리버스/사용자 보고**
- stevebrodie/apogee-one2-linux (9초 워치독 + 하트비트 1차 근거): https://github.com/stevebrodie/apogee-one2-linux
- Loopy Pro 스레드(USB-C iPad 제어 불가): https://forum.loopypro.com/discussion/40824/apogee-one-ipad-pro-usbc-disappointment
- Apple 커뮤니티(USB-C iPad 마이크 불가, Apogee 지원 인용): https://discussions.apple.com/thread/251764012
- Apogee Maestro iOS 앱(2021 이후 정체): https://apps.apple.com/us/app/apogee-maestro/id591261064

**날짜 근거**
- Lightning 2012-09-12: https://en.wikipedia.org/wiki/Lightning_(connector)
- 첫 USB-C iPad Pro 2018-10-30: https://techcrunch.com/2018/10/30/the-ipad-finally-moves-to-usb-c/
- iPhone 15 USB-C 2023-09-12: https://techcrunch.com/2023/09/12/bye-lightning-hello-usb-c/

**프로젝트 내부 근거 파일**
- `resources/firmware-control-path.md`, `resources/onev2-control-protocol-RE.md`, MEMORY.md "Watchdog investigation" / "iAP session machine found"

---

주: 외부 리서치 JSON은 이 기기 펌웨어를 "iAP2 스택"으로 적었으나, 우리 디스어셈블 결과는 **iAP1 프레이밍**이다. 이 노트는 기기 수준에서 **iAP1**을 기준으로 삼았다(2013년 "iPad & Mac" 기기와도 일치).