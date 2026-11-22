<script setup>
// Self-hosted (no API key, no tiny.cloud network call): TinyMCE's core, theme
// and plugins are bundled by Vite like any other dependency, the same way
// @fontsource-variable/inter is. `license-key="gpl"` is TinyMCE's own open
// source declaration, required since v6 to avoid the upgrade-prompt banner.
import Editor from "@tinymce/tinymce-vue";
import "tinymce/tinymce";
import "tinymce/icons/default";
import "tinymce/themes/silver";
import "tinymce/models/dom";
import "tinymce/plugins/lists";
import "tinymce/plugins/advlist";
import "tinymce/plugins/link";
import "tinymce/plugins/autoresize";
import "tinymce/skins/ui/oxide/skin.css";
import uiContentCss from "tinymce/skins/ui/oxide/content.css?inline";
import bodyContentCss from "tinymce/skins/content/default/content.css?inline";

defineProps({
  modelValue: { type: String, default: "" },
  disabled: { type: Boolean, default: false },
});
defineEmits(["update:modelValue"]);

const init = {
  menubar: false,
  statusbar: false,
  plugins: "lists advlist link autoresize",
  toolbar: "bold italic underline | bullist numlist | link | removeformat",
  skin: false,
  content_css: false,
  content_style: uiContentCss + bodyContentCss,
  min_height: 160,
  autoresize_bottom_margin: 16,
  placeholder: "Seating layout, stage setup, AV needs…",
};
</script>

<template>
  <Editor
    :model-value="modelValue"
    :disabled="disabled"
    :init="init"
    license-key="gpl"
    @update:model-value="$emit('update:modelValue', $event)"
  />
</template>
