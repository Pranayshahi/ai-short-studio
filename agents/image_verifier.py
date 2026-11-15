"""
Free, local image-content verification with CLIP (zero-shot).

Answers one question: "does this picture actually show <subject category>?"
by comparing the image against the target description and a set of common
AI-hallucination decoys (faces, anime, cameras, documents, empty scenes...).

Optional dependency: `torch` + `transformers` (model: openai/clip-vit-base-patch32,
~600 MB, downloaded once from Hugging Face). Without them, `verify()` returns
{"available": False} and callers must treat the image as UNVERIFIED - never as passed.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List

MODEL_ID = "openai/clip-vit-base-patch32"

# Target descriptions per subject category (several phrasings improve zero-shot robustness)
CATEGORY_PROMPTS: Dict[str, List[str]] = {
    "firearms": ["a photo of a pistol", "a photo of a handgun", "a photo of a rifle", "a photo of a firearm"],
    "aerospace": ["a photo of a fighter jet", "a photo of a military jet aircraft", "a photo of a jet airplane in flight"],
    "missiles": ["a photo of a missile", "a photo of a rocket launch", "a photo of a missile launcher"],
    "tanks": ["a photo of a tank", "a photo of an armored military vehicle"],
    "naval": ["a photo of a warship", "a photo of a submarine", "a photo of an aircraft carrier ship at sea"],
    "space": ["a photo of a spacecraft", "a photo of a satellite", "a photo of outer space"],
}

# People in the frame: authentic in real photos, but in AI images they are the classic hallucination
# (anime soldiers holding the weapon instead of the weapon itself)
PEOPLE_PROMPTS: List[str] = [
    "a soldier holding a rifle",
    "an anime illustration of a soldier",
    "a person posing with a weapon",
]

# Typical failure modes of weak text-to-image models and irrelevant stock photos
DECOY_PROMPTS: List[str] = [
    "a portrait of a person's face",
    "an anime illustration of a girl",
    "a photo of a person",
    "a photo of a camera",
    "a photo of tools on a workbench",
    "a document with text",
    "an empty landscape",
    "an abstract blurry image",
    "a cartoon drawing",
    "a photo of a propeller airplane",   # e.g. the P-51 in a 'heritage flight' group photo of an F-22
]

_lock = threading.Lock()
_model = None
_processor = None
_device = "cpu"
_load_error: str | None = None


def _load() -> bool:
    global _model, _processor, _device, _load_error
    if _model is not None:
        return True
    if _load_error is not None:
        return False
    with _lock:
        if _model is not None:
            return True
        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            _device = "mps" if torch.backends.mps.is_available() else "cpu"
            _model = CLIPModel.from_pretrained(MODEL_ID).to(_device).eval()
            _processor = CLIPProcessor.from_pretrained(MODEL_ID)
            return True
        except Exception as e:  # missing packages, no network for first download, etc.
            _load_error = f"{type(e).__name__}: {e}"
            return False


def is_available() -> bool:
    return _load()


def verify(image_path: str | Path, category: str, min_target_share: float = 0.45, lenient: bool = False) -> Dict[str, Any]:
    """
    Returns {"available", "passed", "score" (0-100), "best_label", "target_share"}.
    strict (AI images): the target descriptions must reach min_target_share and beat every decoy
    and every other category.
    lenient (real photos already matched to the subject by metadata): reject only a CLEAR mismatch,
    i.e. the subject barely registers (<25%) while a decoy/other category dominates (>50%).
    """
    targets = CATEGORY_PROMPTS.get(category)
    if not targets:
        return {"available": False, "passed": None, "reason": f"No CLIP labels for category '{category}'"}
    if not _load():
        return {"available": False, "passed": None, "reason": f"CLIP unavailable ({_load_error})"}
    try:
        import torch
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        # Other categories are decoys too: a jet checked as "firearms" must lose to "fighter jet",
        # otherwise the closest firearm label wins by default (the C25/AK-47 class of mistake).
        other_cats = {c: p for c, p in CATEGORY_PROMPTS.items() if c != category}
        cross = [lbl for prompts in other_cats.values() for lbl in prompts]
        decoys = DECOY_PROMPTS + PEOPLE_PROMPTS + cross
        labels = targets + decoys
        inputs = _processor(text=labels, images=img, return_tensors="pt", padding=True).to(_device)
        with torch.no_grad():
            probs = _model(**inputs).logits_per_image.softmax(dim=-1)[0].cpu().tolist()
        target_share = sum(probs[: len(targets)])
        decoy_probs = probs[len(targets):]
        # Compare against the strongest competing CATEGORY (summed), and the strongest single decoy
        cat_shares = {c: sum(probs[labels.index(l)] for l in ps) for c, ps in other_cats.items()}
        best_other_cat = max(cat_shares, key=cat_shares.get) if cat_shares else None
        best_decoy = max(decoy_probs)
        best_idx = max(range(len(labels)), key=lambda i: probs[i])
        strongest_other = max([best_decoy] + list(cat_shares.values()))
        people_labels = PEOPLE_PROMPTS + ["a portrait of a person's face", "an anime illustration of a girl", "a photo of a person"]
        people_share = sum(probs[labels.index(l)] for l in people_labels if l in labels)
        if lenient:
            passed = not (target_share < 0.25 and strongest_other > 0.5)
        else:
            passed = (target_share >= min_target_share and target_share > best_decoy
                      and (best_other_cat is None or target_share > cat_shares[best_other_cat])
                      and people_share < 0.45)
        return {
            "available": True,
            "passed": bool(passed),
            "score": int(round(target_share * 100)),
            "target_share": round(target_share, 3),
            "best_label": labels[best_idx],
            "top_decoy": decoys[decoy_probs.index(best_decoy)],
            "top_decoy_share": round(best_decoy, 3),
            "top_other_category": best_other_cat,
            "mode": "lenient" if lenient else "strict",
            "people_share": round(people_share, 3),
        }
    except Exception as e:
        return {"available": False, "passed": None, "reason": f"CLIP inference error: {e}"}
