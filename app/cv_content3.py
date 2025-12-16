# app/cv_content.py

# -----------------------
# 기본 프로필/경력/학력
# -----------------------

cv_profile = {
    "name_ko": "김도원",
    "name_en": "DOWON KIM",
    "email": "kdw59520@gmail.com",
    "github": "https://github.com/Planet-KIM",
    "website": "https://your-portfolio-example",
    "role_ko": "KAIST 의과학대학원(GSMSE) jklab 연구원 · Machine Learning & AI Systems",
    "role_en": "Research Engineer, KAIST GSMSE jklab · Machine Learning & AI Systems",
    "intro_ko": (
        "새로운 데이터셋과 새로운 인공지능 기법을 탐색해 실제 시스템에 도입하는 데 특별한 흥미를 가지고 있습니다. "
        "Transformer와 CNN 기반 모델링, 데이터 분석, 알고리즘 설계에 관심이 있으며, "
        "이러한 ML·시스템 구현 역량을 유전체 서열 분석 문제에 적용해 "
        "BioAI 모델 재현·최적화, multi-model variant interpretation pipeline 개발, "
        "Genomic DataPortal 구축을 수행해왔습니다."
    ),

    "intro_en": (
        "I enjoy exploring new datasets and adopting new machine-learning models into real analysis systems. "
        "My interests include Transformers, CNNs, data-driven modeling, and algorithmic design. "
        "I apply these ML and system-engineering skills to genomic sequence interpretation, "
        "working on model reproduction and optimization, multi-model variant-interpretation pipelines, "
        "and the development of the Genomic DataPortal."
    ),
}

education = {
    "ko": {
        "title": "한밭대학교 정보통신공학과 (학사)",
        "period": "졸업 2021.02",
        "desc": (
            "정보기술대학 정보통신공학과에서 "
            "알고리즘, 네트워크, 신호처리, 머신러닝·딥러닝, 데이터 분석 과목을 이수하며 "
            "전산 이론과 구현 역량을 함께 쌓았습니다."
        ),
        # SCSC-C 프로그램
        "extra": (
            "삼성 Convergence S/W Course for College(SCSC-C)을 통해 "
            "운영체제, 데이터베이스, 자료구조, 소프트웨어 개발 입문 등 핵심 CS 과목을 이수했습니다."
        ),
    },
    "en": {
        "title": "B.S. in Information & Communication Engineering, Hanbat University",
        "period": "2016 – 2022 (Graduated Feb 2022)",
        "desc": (
            "Completed coursework in algorithms, computer networks, signal processing, "
            "machine learning, deep learning, and data analysis."
        ),
        "extra": (
            "Completed Samsung Convergence S/W Course for College (SCSC-C): "
            "Operating Systems, Databases, Data Structures, and Intro to Software Development."
        ),
    },
}

experience = {
    "ko": {
        "position": "연구원, KAIST 의과학대학원(GSMSE) jklab (유전체 분석 연구실)",
        "period": "2022.05 – 현재",
        "bullets": [
            "유전체 분석을 수행하는 jklab에서 BioAI·전산 파트를 담당하며 Genomic DataPortal 및 분석 파이프라인을 설계·개발.",
            "논문 기반 BioAI 모델(SpliceAI, LaBranchoR, MaxEntScan, Optimus 5′UTR 등)을 "
            "reproduce·모듈화하여 연구실 공용 라이브러리 및 pipeline으로 통합.",
            "모델 구조 개선 실험과 평가 pipeline을 구축해 변이 해석 연구의 재현성과 생산성을 향상.",
        ],
    },
    "en": {
        "position": "Researcher, jklab (Genomic Analysis Lab), GSMSE, KAIST",
        "period": "May 2022 – Present",
        "bullets": [
            "Lead the computing and AI track in jklab, designing and developing the Genomic DataPortal and analysis pipelines.",
            "Reproduce and modularize paper-based BioAI models (SpliceAI, LaBranchoR, MaxEntScan, Optimus 5′UTR, etc.) "
            "into shared libraries and pipelines.",
            "Build architecture-experiment and evaluation pipelines to improve the reproducibility and productivity of "
            "variant-interpretation studies.",
        ],
    },
}

# -----------------------
# 산업 경력 (Industry Experience)
# -----------------------

industry = {
    "ko": [
        {
            "company": "㈜몰팩바이오",
            "role": "연구원",
            "period": "2021.02 – 2022.03",
            "desc": "의료 진단용 데이터 분석 및 연구개발 업무 수행, Python 기반 데이터 처리·모델링 경험.",
        },
        {
            "company": "㈜사라 기술연구소",
            "role": "주임 연구원",
            "period": "2020.09 – 2021.01",
            "desc": "C/Java/Python 응용 프로그램 및 웹 서비스 개발, MySQL 기반 데이터베이스 설계·구현.",
        },
    ],
    "en": [
        {
            "company": "MolpaxBio Co., Ltd.",
            "role": "Research Engineer",
            "period": "Feb 2021 – Mar 2022",
            "desc": "Data analysis and R&D for medical diagnostics, including Python-based data processing and modeling.",
        },
        {
            "company": "SARA Tech Lab",
            "role": "Junior Research Engineer",
            "period": "Sep 2020 – Jan 2021",
            "desc": "Developed C/Java/Python applications and web services, and designed MySQL-based databases.",
        },
    ],
}

# -----------------------
# Skill 색 팔레트 + 항목
# -----------------------

skill_palette = {
    "ai": "#e7f5ff",       # 파란계열: AI / 모델링
    "bioai": "#fff0f6",    # 핑크: BioAI 도구들
    "python": "#fff3bf",   # 노랑: Python 기반 프레임워크/최적화
    "stats": "#e6fcf5",    # 민트: 통계/평가
    "data": "#e3fafc",     # 청록: 데이터/전처리
    "infra": "#f8f0fc",    # 보라: 인프라/엔지니어링
    "default": "#f1f3f5",  # 기본
}

skills = {
    "ml": [
        {"label": "PyTorch", "kind": "python"},
        {"label": "TensorFlow", "kind": "python"},
        {"label": "Transformer", "kind": "ai"},
        {"label": "CNN", "kind": "ai"},
        {"label": "Dilated Conv", "kind": "ai"},
        {"label": "ResNet", "kind": "ai"},
        {"label": "Sequence Modeling", "kind": "ai"},
        {"label": "Algorithm design & model optimization", "kind": "ai"},
    ],
    "bioai": [
        {"label": "SpliceAI", "kind": "bioai"},
        {"label": "MaxEntScan", "kind": "bioai"},
        {"label": "LaBranchoR", "kind": "bioai"},
        {"label": "Optimus 5′UTR", "kind": "bioai"},
        {"label": "VEP", "kind": "bioai"},
    ],
    "se": [
        {"label": "Python 최적화", "kind": "python"},
        {"label": "모듈화 · 리팩토링", "kind": "infra"},
        {"label": "대규모 코드베이스 재설계", "kind": "infra"},
        {"label": "API 설계/구현", "kind": "infra"},
        {"label": "ML Pipeline 구축", "kind": "ai"},
        {"label": "GPU 최적화", "kind": "infra"},
        {"label": "병렬 처리", "kind": "infra"},
        {"label": "Production 배포", "kind": "infra"},
    ],
    "data": [
        {"label": "Genomic sequence data", "kind": "data"},
        {"label": "Variant datasets", "kind": "data"},
        {"label": "대규모 전처리", "kind": "data"},
        {"label": "모델 평가 자동화", "kind": "stats"},
        {"label": "통계적 분석", "kind": "stats"},
        {"label": "Computational genomics & sequence analysis", "kind": "data"},
    ],
}

# -----------------------
# Projects (기간 정렬용 start/end)
# -----------------------

projects = [
    {
        "id": "offtarget_conservation",
        "start_year": 2024,
        "end_year": None,
        "title_ko": "Cross-species Off-target Conservation 분석 도구 개발",
        "title_en": "Cross-species Off-target Conservation Analysis Tool",
        "meta_ko": "CRISPR/ASO 설계 · 종 간 서열 보존도 기반 off-target 위험도 정량화 · 웹 서비스화",
        "meta_en": "CRISPR/ASO design · Cross-species conservation-based off-target risk scoring · Web deployment",
        "bullets_ko": [
            "실험실 요청을 기반으로 인간–마우스–래빗 등 주요 모델동물 간 서열 보존도를 비교하여 off-target 위험을 정량화하는 도구를 직접 제안·설계·구현.",
            "multi-species alignment, edit distance, wobble-aware mismatch 모델을 결합하여 종별 보존도와 off-target 위험도를 계산하는 알고리즘 개발.",
            "ASO-design 결과 파일을 입력으로 받아 각 후보 ASO의 cross-species conservation 지표를 자동 계산하고 CSV로 반환하는 파이프라인 구축.",
            "해당 알고리즘을 모듈화(ASOPIPE)하고 웹 UI(ASOVIEW)를 제작하여 연구실 내에서 실제 서비스로 운영, 전임상 실험 설계 지원.",
        ],
        "bullets_en": [
            "Designed and implemented a cross-species off-target analysis tool quantifying sequence conservation among human, mouse, rabbit, and other model organisms.",
            "Developed algorithms integrating multi-species alignment, edit-distance scoring, and wobble-aware mismatch modeling to jointly assess conservation and off-target risks.",
            "Integrated the tool with the aso-design pipeline to automatically compute conservation metrics for each ASO candidate and export structured CSV outputs.",
            "Modularized the analysis pipeline (ASOPIPE) and built a web UI (ASOVIEW), deployed as a real internal service used by the research lab for preclinical decision-making.",
        ],
        "links": [
            {"label": "GitHub: ASOPIPE (module)", "url": "https://github.com/Planet-KIM/ASOPIPE"},
            {"label": "GitHub: ASOVIEW (web UI)", "url": "https://github.com/Planet-KIM/asoview"},
            {"label": "Live Service (Internal Lab Deployment)", "url": "http://143.248.208.160:4043/tasks"},
        ],
    },
    {
        "id": "aso",
        "start_year": 2023,
        "end_year": None,
        "title_ko": "ASO Amenability 분석 플랫폼 개발 · Nature 2023 Backend",
        "title_en": "ASO Amenability Analysis Platform · Nature 2023 Backend",
        "meta_ko": "Multi-model integration · Variant interpretation 시스템 · Genomic DataPortal",
        "meta_en": "Multi-model integration · Variant interpretation system · Genomic DataPortal backend",
        "bullets_ko": [
            "SpliceAI, MaxEntScan, LaBranchoR, VEP, Optimus 5′UTR 등을 재현·최적화하고 공통 Python 모듈로 통합.",
            "논문 저자들이 정의한 taxonomy 및 의사결정 규칙을 기반으로, 여러 모델의 score를 결합하는 "
            "variant interpretation pipeline을 구현·자동화.",
            "Genomic DataPortal에 배포하여 브라우저 기반 변이 탐색 도구로 제공.",
            "이 플랫폼이 연구실 Nature(2023) 논문의 ASO amenability 분석에 계산 백엔드로 사용되었으며, "
            "해당 backend의 설계·구현을 담당.",
        ],
        "bullets_en": [
            "Reproduced and optimized SpliceAI, MaxEntScan, LaBranchoR, VEP, Optimus 5′UTR and integrated them into a shared Python module.",
            "Implemented and automated a variant interpretation pipeline that combines scores from multiple models, "
            "based on the taxonomy and decision rules defined by the paper’s authors.",
            "Deployed the pipeline to the lab’s Genomic DataPortal for browser-based variant exploration.",
            "The platform served as the computational backend for ASO amenability analyses in a Nature (2023) study from the lab, "
            "for which I designed and implemented the backend system.",
        ],
        "links": [
            {
                "label": "DataPortal (ASO Amenability)",
                "url": "http://143.248.208.160:4042/asoamenable",
            },
            {
                "label": "GitHub: jklabkaist/third_party",
                "url": "https://github.com/jklabkaist/third_party",
            },
        ],
    },
    {
        "id": "optimus5utr",
        "start_year": 2023,
        "end_year": 2024,
        "title_ko": "Optimus 5′UTR 모델 재현 및 확장",
        "title_en": "Optimus 5′UTR Reproduction and Extension",
        "meta_ko": "Nature Communications 기반 모델 재현 · 신규 sequence model 개발",
        "meta_en": "Nature Communications-based model reproduction · New sequence models",
        "bullets_ko": [
            "Optimus 5′UTR 논문과 공식 구현을 분석하여 모델 전체를 재현하고, 연구실 환경에 맞는 reproducible workflow 구성.",
            "레거시 코드 의존성을 제거하고 Python/PyTorch 기반으로 현대화하여 실험을 쉽게 재현·확장할 수 있게 설계.",
            "5′UTR 변이 영향 분석을 위해 신규 sequence model 모듈(jkutr5/extensions)을 설계·구현하여 현재 jklab pipeline에서 사용.",
        ],
        "bullets_en": [
            "Analyzed the Optimus 5′UTR paper and reference implementation and fully reproduced the model with a reproducible workflow.",
            "Modernized the codebase by removing legacy dependencies and re-implementing it in Python/PyTorch.",
            "Developed new sequence model modules (jkutr5/extensions) for 5′UTR variant effect analysis, now used in jklab’s pipelines.",
        ],
        "links": [
            {
                "label": "GitHub: jklabkaist/jkutr5",
                "url": "https://github.com/jklabkaist/jkutr5",
            },
        ],
    },
    {
        "id": "spliceai",
        "start_year": 2022,
        "end_year": 2024,
        "title_ko": "SpliceAI 재현 및 모델 구조 개선 실험",
        "title_en": "SpliceAI Reproduction and Architecture Experiments",
        "meta_ko": "TensorFlow → PyTorch 재구현 · Dilated Conv 한계 분석 · DataPortal 배포",
        "meta_en": "TensorFlow → PyTorch · Dilated Conv limitations · DataPortal deployment",
        "bullets_ko": [
            "SpliceAI 논문 구현을 분석·재현하고 TensorFlow 기반 재학습 후, 연구실 환경에서 사용하기 위해 전체 모델을 PyTorch로 재구현.",
            "Dilated convolution 구조에서 발생하는 정보 손실을 분석하고 ResNet block 추가, dilation 조정, Transformer 기반 대체 구조 등 여러 개선 실험 수행.",
            "최적화된 모델을 Genomic DataPortal에 배포하여 변이별 splice 영향 예측을 웹 인터페이스로 제공.",
        ],
        "bullets_en": [
            "Reproduced the original SpliceAI implementation and training in TensorFlow, then re-implemented the entire model in PyTorch.",
            "Investigated information loss in dilated convolutions and experimented with ResNet blocks, dilation adjustments, and Transformer-based alternatives.",
            "Deployed the optimized model to the Genomic DataPortal to provide web-based splice-effect predictions for variants.",
        ],
        "links": [
            {
                "label": "DataPortal (SpliceAI)",
                "url": "http://143.248.208.160:4042/spliceai",
            },
            {
                "label": "GitHub: jkspliceai",
                "url": "https://github.com/jklabkaist/jkspliceai",
            },
        ],
    },
    {
        "id": "labranchor",
        "start_year": 2022,
        "end_year": 2023,
        "title_ko": "LaBranchoR Python 재구현 및 최적화",
        "title_en": "LaBranchoR Python Re-implementation and Optimization",
        "meta_ko": "Legacy 스크립트 → Modern PyTorch · RNA branchpoint 분석",
        "meta_en": "Legacy scripts → Modern PyTorch · RNA branchpoint analysis",
        "bullets_ko": [
            "오래된 스크립트 기반 LaBranchoR 구현을 분석하여 Python/PyTorch로 완전 재구현하고 전처리–embedding–training pipeline 재설계.",
            "입출력 및 구조를 정리해 다른 모델들과 함께 사용할 수 있는 공통 interface로 정리, 속도와 재현성 향상.",
            "현재 jklab의 RNA branchpoint 분석 파이프라인에서 실제 사용 중.",
        ],
        "bullets_en": [
            "Analyzed the legacy script-based LaBranchoR implementation and fully re-implemented it in Python/PyTorch.",
            "Refactored I/O and abstractions to provide a clean interface compatible with other models, improving speed and reproducibility.",
            "The resulting model is used in jklab’s RNA branchpoint analysis pipeline.",
        ],
        "links": [
            {
                "label": "GitHub: Planet-KIM/LaBranchoR",
                "url": "https://github.com/Planet-KIM/LaBranchoR",
            },
        ],
    },
    {
        "id": "maxentscan",
        "start_year": 2022,
        "end_year": 2023,
        "title_ko": "MaxEntScan Python 재구현 및 Multi-Model Pipeline 통합",
        "title_en": "MaxEntScan Python Re-implementation and Integration",
        "meta_ko": "Perl/C → Python 재설계 · Feature scoring 개선",
        "meta_en": "Perl/C → Python · Integration into multi-model pipelines",
        "bullets_ko": [
            "Perl/C 기반 MaxEntScan을 분석해 Python으로 완전히 재설계하고 reproducible 벤치마크와 테스트 구성.",
            "Feature scoring을 개선하고 SpliceAI·LaBranchoR 등과 함께 사용할 수 있도록 현대적인 ML pipeline 형태로 통합.",
            "ASO Amenability·SpliceAI 기반 multi-model pipeline의 핵심 모듈로 사용되며 jklab Genomic DataPortal에서도 활용.",
        ],
        "bullets_en": [
            "Re-designed the original Perl/C-based MaxEntScan in Python with reproducible benchmarks and tests.",
            "Improved feature scoring and integrated MaxEntScan with SpliceAI, LaBranchoR, and others in modern ML pipelines.",
            "Now serves as a core component in multi-model pipelines for ASO Amenability and SpliceAI-based analyses, and in jklab’s Genomic DataPortal.",
        ],
        "links": [
            {
                "label": "GitHub: Planet-KIM/MaxEntScan",
                "url": "https://github.com/Planet-KIM/MaxEntScan",
            },
        ],
    },
    {
        "id": "dataportal",
        "start_year": 2022,
        "end_year": None,
        "title_ko": "Genomic DataPortal: AI·DB 통합 Variant Interpretation 플랫폼",
        "title_en": "Genomic DataPortal: AI & DB-integrated Variant Interpretation Platform",
        "meta_ko": "Varsome 유사 웹 플랫폼 · AI 모델 + VEP/gnomAD/TOPMed 통합 · Variant 분석 시스템",
        "meta_en": "Varsome-like web platform · AI models + VEP/gnomAD/TOPMed integration · Variant analysis system",
        "bullets_ko": [
            "변이를 입력하면 SpliceAI, LaBranchoR, MaxEntScan, Optimus5′UTR, ASO pipeline 등 여러 AI 모델의 예측과 "
            "VEP, gnomAD, TOPMed와 같은 외부 데이터베이스 annotation을 통합해 보여주는 Varsome 유사 variant interpretation 플랫폼을 설계·구현.",
            "모델 inference orchestration, feature aggregation, score normalization을 통합한 variant-centric backend 엔진을 설계하고, "
            "REST API 기반 서버와 웹 시각화 UI를 포함한 full-stack 시스템을 구축.",
            "연구실 서버에서 production 서비스로 운영하여, 연구자들이 일상적으로 변이 해석 및 ASO 분석에 활용하도록 지원.",
        ],
        "bullets_en": [
            "Developed an AI-based variant interpretation platform similar to Varsome, integrating predictions from multiple ML models "
            "(SpliceAI, LaBranchoR, MaxEntScan, Optimus5′UTR, ASO pipeline) with external genomic databases such as VEP, gnomAD, and TOPMed.",
            "Designed a variant-centric backend engine that combines model orchestration, feature aggregation, and score normalization, "
            "and implemented a full-stack system including REST APIs and a web-based visualization UI.",
            "Deployed the system as a production service on the lab’s server, enabling researchers to routinely perform variant interpretation and ASO-related analysis.",
        ],
        "links": [
            {
                "label": "Genomic DataPortal (Variant analysis)",
                "url": "http://143.248.208.160:4042/",
            },
            {
                "label": "GitHub: jkportal",
                "url": "https://github.com/Planet-KIM/jkportal",
            },
        ],
    },
]
