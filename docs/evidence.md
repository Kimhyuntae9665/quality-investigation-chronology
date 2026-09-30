# 공개 기업 근거와 재현 경계

| 출처·날짜 | 출처의 주장 | 우리 재현 범위 | 검증하지 않은 부분 |
|---|---|---|---|
| [Catalent 보도자료](https://www.catalent.com/news/catalent-launches-qai-to-reimagine-quality-assurance-for-its-manufacturing-services), 2026-06-16 | Qai 출시. 일탈·불만 QMS 과정에 기업 데이터를 활용해 분석, 원인 조사와 CAPA 초안을 돕는다고 회사가 설명 | 가상 포장 조사에서 출처 시간선과 검토 요청을 정리 | 회사의 실제 데이터, 성능 수치, 비공개 시스템 설계 |
| [Microsoft 고객 사례](https://www.microsoft.com/en/customers/story/27171-catalent-azure-openai-in-foundry-models), 2026-09-09 | 거의 완료된 배포, 품질 전문가의 기록된 인간 검증, Qai의 읽기 전용 접근과 GMP 기록 비수정이라고 고객·공급자 측이 설명 | 읽기 전용 원문 조회와 사람 검토 인계 경계 | GMP 적격성, 규제 적합성, Catalent 구현과의 동등성 |

Microsoft 사례가 밝힌 Azure·Foundry·Fabric 아키텍처를 이 로컬 Python 앱의 기술 구성으로 쓰지 않습니다. 초기 생산성 징후나 기업 발표를 우리 프로토타입의 ROI·품질 개선 증거로 바꾸지 않습니다. 실제 제약 정보, 환자 데이터, 제조 기록은 사용하지 않습니다.
