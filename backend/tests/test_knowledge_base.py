import tempfile
import unittest
from pathlib import Path

from app.knowledge_base import build_knowledge_block, relevant_notes
from app.migration_service import _local_header_context


class KnowledgeBaseTests(unittest.TestCase):
    def test_retrieves_warp_note_for_shuffle_code(self):
        src = "val = __shfl_down_sync(mask, val, offset);"
        ids = [n.id for n in relevant_notes(src)]
        self.assertIn("warp-size", ids)

    def test_retrieves_torch_note_for_python(self):
        src = "if torch.cuda.is_available():\n    model = model.to('cuda')"
        ids = [n.id for n in relevant_notes(src)]
        self.assertIn("torch-python", ids)

    def test_retrieves_cmake_and_nvcc_notes_for_build_file(self):
        src = "enable_language(CUDA)\nset(CMAKE_CUDA_ARCHITECTURES 80)\nnvcc -arch=sm_80"
        ids = [n.id for n in relevant_notes(src)]
        self.assertIn("cmake-hip", ids)
        self.assertIn("build-nvcc", ids)

    def test_no_notes_for_plain_code(self):
        self.assertEqual(relevant_notes("print('hello')"), [])
        self.assertEqual(build_knowledge_block("print('hello')"), "")

    def test_block_is_capped(self):
        src = (
            "cudnn thrust:: cub:: nccl wmma torch.cuda CUDAExtension enable_language(CUDA) "
            "nvidia/cuda cuInit nvrtc <<< nvcc cudaGraph cusparse cudaMallocManaged __half"
        )
        block = build_knowledge_block(src)
        self.assertTrue(block.startswith("Grounding notes"))
        self.assertLessEqual(len(block), 3200)

    def test_dnn_flagged_for_manual_review(self):
        block = build_knowledge_block("cudnnConvolutionForward(handle, ...);")
        self.assertIn("MIOpen", block)
        self.assertIn("manual review", block)


class HeaderContextTests(unittest.TestCase):
    def test_includes_local_header_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "src").mkdir()
            (workspace / "src" / "ops.h").write_text("#define TILE 32\nvoid launch();\n", encoding="utf-8")
            source = '#include "ops.h"\n#include <cuda_runtime.h>\n'
            block = _local_header_context(workspace, "src/kernel.cu", source)
            self.assertIn("ops.h", block)
            self.assertIn("#define TILE 32", block)
            self.assertIn("read-only", block)

    def test_ignores_missing_and_external_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "src").mkdir()
            source = '#include "missing.h"\n#include "../../../etc/passwd"\n'
            block = _local_header_context(workspace, "src/kernel.cu", source)
            self.assertEqual(block, "")


if __name__ == "__main__":
    unittest.main()
