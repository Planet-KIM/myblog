# ============================================================
#  자주 쓰는 배포/운영 명령 모음  —  `make <타깃>`
#  (명령을 외울 필요 없이 make 한 줄로)
# ============================================================
.PHONY: help deploy up rebuild-editor migrate logs ps down restart build

help:            ## 사용 가능한 명령 목록
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

deploy:          ## 전체 배포: 에디터 빌드 + 이미지 빌드 + 기동 + DB 마이그레이션(자동)
	docker compose up -d --build
	@echo "✅ 배포 완료 →  http://localhost:5052"

up: deploy       ## deploy 의 별칭

rebuild-editor:  ## 에디터(TipTap) 번들만 강제 재빌드 (에디터 소스 수정 후)
	FORCE_EDITOR_BUILD=1 docker compose run --rm editor-build
	docker compose restart web

migrate:         ## DB 마이그레이션 수동 실행 (보통은 기동 시 자동)
	docker compose exec web alembic upgrade head

logs:            ## web 로그 실시간 보기
	docker compose logs -f web

ps:              ## 컨테이너 상태
	docker compose ps

restart:         ## web 재시작
	docker compose restart web

down:            ## 전체 중지
	docker compose down
