import { defineComponent, mergeProps, useSSRContext } from "vue";
import { ssrRenderAttrs, ssrInterpolate } from "vue/server-renderer";
import { _ as _export_sfc } from "../entry-server.js";
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "SectionTitle",
  __ssrInlineRender: true,
  props: {
    title: {},
    description: {},
    tag: {},
    center: { type: Boolean }
  },
  setup(__props) {
    return (_ctx, _push, _parent, _attrs) => {
      _push(`<div${ssrRenderAttrs(mergeProps({
        class: ["section-title", { "text-center": __props.center }]
      }, _attrs))} data-v-39eac46e>`);
      if (__props.tag) {
        _push(`<span class="tag" data-v-39eac46e>${ssrInterpolate(__props.tag)}</span>`);
      } else {
        _push(`<!---->`);
      }
      _push(`<h2 data-v-39eac46e>${ssrInterpolate(__props.title)}</h2>`);
      if (__props.description) {
        _push(`<p data-v-39eac46e>${ssrInterpolate(__props.description)}</p>`);
      } else {
        _push(`<!---->`);
      }
      _push(`</div>`);
    };
  }
});
const _sfc_setup = _sfc_main.setup;
_sfc_main.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/components/SectionTitle.vue");
  return _sfc_setup ? _sfc_setup(props, ctx) : void 0;
};
const SectionTitle = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-39eac46e"]]);
export {
  SectionTitle as S
};
