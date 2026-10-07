<!DOCTYPE html>
<html lang="en">

<head>

    <meta charset="UTF-8">

    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <title>Reschedule Appointment</title>

    <style>

        body {
            font-family: Arial, sans-serif;
            background: #f5f7fb;
            margin: 0;
            padding: 0;
        }

        .container {
            width: 90%;
            max-width: 650px;
            margin: 50px auto;
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }

        h1 {
            margin-bottom: 25px;
        }

        .info {
            background: #f1f5f9;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 25px;
        }

        label {
            display: block;
            margin-top: 15px;
            margin-bottom: 6px;
            font-weight: bold;
        }

        input,
        select {

            width: 100%;
            padding: 11px;
            border: 1px solid #ccc;
            border-radius: 6px;
            box-sizing: border-box;

        }

        button {

            margin-top: 25px;
            width: 100%;
            padding: 13px;
            border: none;
            border-radius: 7px;
            background: #2563eb;
            color: white;
            font-size: 16px;
            cursor: pointer;

        }

        button:hover {
            background: #1d4ed8;
        }

        .back {

            display: block;
            margin-top: 15px;
            text-align: center;
            text-decoration: none;
            color: #555;

        }

    </style>

</head>


<body>


<div class="container">


    <h1>
        Reschedule Appointment
    </h1>


    <!-- =========================================
         CURRENT APPOINTMENT
    ========================================== -->

    <div class="info">

        <p>
            <strong>Doctor:</strong>

            {{ doctor.name if doctor else "Doctor" }}

        </p>


        <p>

            <strong>Current Date:</strong>

            {{ appointment.appointment_date }}

        </p>


        <p>

            <strong>Current Time:</strong>

            {{ appointment.start_time }}

            -

            {{ appointment.end_time }}

        </p>


        <p>

            <strong>Visit Type:</strong>

            {{ appointment.visit_type }}

        </p>

    </div>


    <!-- =========================================
         RESCHEDULE FORM
    ========================================== -->

    <form

        method="POST"

        action="/appointments/{{ appointment.id }}/reschedule"

    >


        <!-- DATE -->

        <label for="appointment_date">

            New Appointment Date

        </label>


        <input

            type="date"

            id="appointment_date"

            name="appointment_date"

            required

        >


        <!-- START TIME -->

        <label for="start_time">

            New Start Time

        </label>


        <input

            type="time"

            id="start_time"

            name="start_time"

            required

        >


        <!-- END TIME -->

        <label for="end_time">

            New End Time

        </label>


        <input

            type="time"

            id="end_time"

            name="end_time"

            required

        >


        <!-- SUBMIT -->

        <button type="submit">

            Confirm Reschedule

        </button>


    </form>


    <!-- BACK -->

    <a

        href="/appointments"

        class="back"

    >

        ← Back to My Appointments

    </a>


</div>


</body>

</html>