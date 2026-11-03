def analyze_dc(voltage_v, resistance_ohm):
    current_a = voltage_v / resistance_ohm
    power_w = voltage_v * current_a
    return {"current_a": current_a, "power_w": power_w}

if __name__ == "__main__":
    print("=== โปรแกรมคำนวณวงจรไฟตรง (DC Circuit Calculator) ===")
    print("พิมพ์ 'q' แล้วกด Enter เพื่อออกจากโปรแกรม\n")
    
    while True:
        try:
            # รับค่าแรงดันไฟฟ้า
            v_input = input("ป้อนค่าแรงดันไฟฟ้า (V): ")
            if v_input.lower() == 'q':
                print("จบการทำงาน")
                break
            voltage = float(v_input)
            
            # รับค่าความต้านทาน
            r_input = input("ป้อนค่าความต้านทาน (Ohm): ")
            if r_input.lower() == 'q':
                print("จบการทำงาน")
                break
            resistance = float(r_input)
            
            # ตรวจสอบเพื่อป้องกันการหารด้วยศูนย์
            if resistance <= 0:
                print("[!] ข้อผิดพลาด: ความต้านทานต้องมีค่ามากกว่า 0\n")
                continue
                
            # เรียกใช้ฟังก์ชันคำนวณ
            result = analyze_dc(voltage, resistance)
            
            # แสดงผลลัพธ์
            print("\n--- ผลการคำนวณ ---")
            print(f"กระแสไฟฟ้า (I) : {result['current_a']:.4f} A")
            print(f"กำลังไฟฟ้า (P) : {result['power_w']:.4f} W")
            print("-" * 30 + "\n")
            
        except ValueError:
            print("[!] ข้อผิดพลาด: กรุณาป้อนข้อมูลเป็นตัวเลขเท่านั้น\n")