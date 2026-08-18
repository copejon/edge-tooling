.PHONY: setup-githooks lint-markdown lint-all-markdown lint-fix-markdown lint-shellcheck lint-skills lint-all-skills lint-gofmt lint-fix-gofmt

setup-githooks:
	git config core.hooksPath .githooks
	@echo "Git hooks configured to use .githooks/"

lint-markdown:
	scripts/lint-markdown.sh --pre-commit

lint-all-markdown:
	scripts/lint-markdown.sh --check-all-files

lint-fix-markdown:
	scripts/lint-markdown.sh --fix

lint-shellcheck:
	scripts/lint-shellcheck.sh

lint-skills:
	scripts/lint-skills.py

lint-all-skills:
	scripts/lint-skills.py --check-all-files

lint-gofmt:
	scripts/lint-gofmt.sh

lint-fix-gofmt:
	scripts/lint-gofmt.sh --fix
