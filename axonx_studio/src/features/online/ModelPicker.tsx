import { useTranslation } from "react-i18next";
import { Picker } from "../../shared/ui/Select";

export function ModelPicker({
  models,
  value,
  onChange,
  label,
  labels,
}: {
  label?: string;
  labels?: Record<string, string>;
  models: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <Picker
      className="online-model-picker"
      label={label || t("onlineWorkbench.model")}
      options={models.map((value) => ({
        value,
        label: labels?.[value] || value,
      }))}
      value={value}
      onChange={onChange}
    />
  );
}
