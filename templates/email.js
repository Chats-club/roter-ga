function handleSubmit() {
  const message = document.querySelector("textarea").value;

  if (!message.trim()) {
    alert("Vui lòng nhập nội dung request!");
    return;
  }

  const templateParams = {
    from_name: "Nhân viên", // hoặc lấy từ session/login nếu có
    message: message,
    time: new Date().toLocaleString("vi-VN"),
  };

  emailjs.send("service_bi2hxqg", "template_x6vqwo1", templateParams)
    .then(() => {
      alert("Request đã được gửi!");
      document.querySelector("textarea").value = "";
    })
    .catch((error) => {
      alert("Gửi thất bại, thử lại!");
      console.error(error);
    });
}