PDF=build/fhops-softx.pdf
TEX=fhops-softx.tex
BUILD_DIR=build
ASSETS_SCRIPT=scripts/generate_assets.sh
ELSARTICLE_CLS=elsarticle/elsarticle.cls
LATEX_ENV=TEXINPUTS=.:elsarticle//: BSTINPUTS=.:elsarticle//:

.PHONY: all assets pdf clean default manuscript-benchmarks manuscript-benchmarks-fast

all: clean assets pdf

assets:
	bash $(ASSETS_SCRIPT)

manuscript-benchmarks:
	bash scripts/run_manuscript_benchmarks.sh

manuscript-benchmarks-fast:
	FHOPS_ASSETS_FAST=1 bash scripts/run_manuscript_benchmarks.sh

pdf: $(PDF)

$(ELSARTICLE_CLS): elsarticle/elsarticle.ins elsarticle/elsarticle.dtx
	cd elsarticle && latex elsarticle.ins

$(PDF): $(TEX) $(ELSARTICLE_CLS)
	mkdir -p $(BUILD_DIR)
	$(LATEX_ENV) latexmk -pdf -interaction=nonstopmode -output-directory=$(BUILD_DIR) -auxdir=$(BUILD_DIR) $(TEX)

default: pdf

clean:
	latexmk -C -output-directory=$(BUILD_DIR) -auxdir=$(BUILD_DIR)
	$(RM) -r $(BUILD_DIR)
