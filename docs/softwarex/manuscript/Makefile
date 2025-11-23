PDF=build/fhops-softx.pdf
TEX=fhops-softx.tex
BUILD_DIR=build

$(PDF): $(TEX)
	mkdir -p $(BUILD_DIR)
	latexmk -pdf -interaction=nonstopmode -output-directory=$(BUILD_DIR) $(TEX)

.PHONY: clean
default: $(PDF)

clean:
	latexmk -C -output-directory=$(BUILD_DIR)
	$(RM) -r $(BUILD_DIR)
