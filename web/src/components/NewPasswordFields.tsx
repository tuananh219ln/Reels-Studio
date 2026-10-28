import { Form, Input } from "antd";

const MIN = 8;

/** New password typed twice: at least 8 characters and both entries must match. */
export default function NewPasswordFields() {
  return (
    <>
      <Form.Item
        label="Mật khẩu mới"
        name="new_password"
        rules={[
          { required: true, message: "Nhập mật khẩu mới" },
          { min: MIN, message: `Mật khẩu phải có ít nhất ${MIN} ký tự` },
        ]}
      >
        <Input.Password autoComplete="new-password" />
      </Form.Item>
      <Form.Item
        label="Nhập lại mật khẩu mới"
        name="confirm_password"
        dependencies={["new_password"]}
        rules={[
          { required: true, message: "Nhập lại mật khẩu mới" },
          ({ getFieldValue }) => ({
            validator: (_, value) =>
              !value || value === getFieldValue("new_password")
                ? Promise.resolve()
                : Promise.reject(new Error("Hai lần nhập mật khẩu không khớp")),
          }),
        ]}
      >
        <Input.Password autoComplete="new-password" />
      </Form.Item>
    </>
  );
}
