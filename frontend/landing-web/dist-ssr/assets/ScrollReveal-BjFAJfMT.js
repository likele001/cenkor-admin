import { defineComponent, ref, computed, onMounted, onUnmounted, mergeProps, useSSRContext } from "vue";
import { ssrRenderAttrs, ssrRenderSlot } from "vue/server-renderer";
import { _ as _export_sfc } from "../entry-server.js";
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "ScrollReveal",
  __ssrInlineRender: true,
  props: {
    animation: { default: "fade-up" },
    delay: { default: 0 }
  },
  setup(__props) {
    const props = __props;
    const element = ref(null);
    const isVisible = ref(false);
    const isPending = ref(false);
    let observer = null;
    const delayStyle = computed(() => {
      return props.delay > 0 ? { transitionDelay: `${props.delay}ms` } : {};
    });
    onMounted(() => {
      if (typeof IntersectionObserver === "undefined") return;
      isPending.value = true;
      observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              isVisible.value = true;
              isPending.value = false;
              observer == null ? void 0 : observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.1 }
      );
      if (element.value) {
        observer.observe(element.value);
      }
    });
    onUnmounted(() => {
      observer == null ? void 0 : observer.disconnect();
    });
    return (_ctx, _push, _parent, _attrs) => {
      _push(`<div${ssrRenderAttrs(mergeProps({
        ref_key: "element",
        ref: element,
        class: ["scroll-reveal", [__props.animation, { visible: isVisible.value, pending: isPending.value }]],
        style: delayStyle.value
      }, _attrs))} data-v-cfb262de>`);
      ssrRenderSlot(_ctx.$slots, "default", {}, null, _push, _parent);
      _push(`</div>`);
    };
  }
});
const _sfc_setup = _sfc_main.setup;
_sfc_main.setup = (props, ctx) => {
  const ssrContext = useSSRContext();
  (ssrContext.modules || (ssrContext.modules = /* @__PURE__ */ new Set())).add("src/components/ScrollReveal.vue");
  return _sfc_setup ? _sfc_setup(props, ctx) : void 0;
};
const ScrollReveal = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-cfb262de"]]);
export {
  ScrollReveal as S
};
